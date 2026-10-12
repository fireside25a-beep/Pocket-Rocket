/*
 * Pocket Rocket Workspace
 *
 * A small, local-only GTK4 client for the native/Python Lumus boundary.  It is
 * deliberately a separate process: the model runtime owns memory and
 * arithmetic certificates; this process owns presentation and repository
 * navigation.  All subprocess calls use fork/exec with fixed argv vectors.
 */
#define _POSIX_C_SOURCE 200809L

#include <gtk/gtk.h>
#include <glib/gstdio.h>

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define MAX_FILE_BYTES (4U * 1024U * 1024U)
#define MAX_COMMAND_BYTES (2U * 1024U * 1024U)
#define MAX_FILES 2500U
#define DEFAULT_PORT 8000

typedef struct {
    GtkApplication *application;
    GtkWindow *window;
    GtkListBox *files;
    GtkTextBuffer *editor;
    GtkTextBuffer *output;
    GtkEntry *prompt;
    GtkEntry *task;
    GtkEntry *commit_message;
    GtkSpinButton *port;
    GtkCheckButton *save_confirm;
    GtkCheckButton *commit_confirm;
    GtkLabel *status;
    gchar *root;
    gchar *selected;
} Workspace;

typedef struct {
    Workspace *workspace;
    gchar *label;
    gchar *text;
    gint exit_status;
} CommandResult;

typedef struct {
    Workspace *workspace;
    gchar *prompt;
    guint16 port;
} AskJob;

typedef struct {
    Workspace *workspace;
    gchar *prompt;
    gchar *response;
    gchar *error;
    gint status;
    gboolean ok;
} AskResult;

typedef struct {
    Workspace *workspace;
    gchar *response;
    gchar *error;
    guint16 port;
    gint status;
    gboolean ok;
} ResetJob;

static void set_status(Workspace *workspace, const gchar *message) {
    gtk_label_set_text(workspace->status, message);
}

static void output_text(Workspace *workspace, const gchar *text) {
    GtkTextIter end;
    gtk_text_buffer_get_end_iter(workspace->output, &end);
    gtk_text_buffer_insert(workspace->output, &end, text, -1);
}

static void output_line(Workspace *workspace, const gchar *label, const gchar *text) {
    gchar *line = g_strdup_printf("\n[%s]\n%s\n", label, text != NULL ? text : "");
    output_text(workspace, line);
    g_free(line);
}

static gboolean path_inside_root(const Workspace *workspace, const gchar *path) {
    gsize root_len = strlen(workspace->root);
    return g_str_has_prefix(path, workspace->root) &&
           (path[root_len] == '\0' || path[root_len] == G_DIR_SEPARATOR);
}

static gchar *safe_existing_file(const Workspace *workspace, const gchar *relative) {
    if (relative == NULL || *relative == '\0' || g_path_is_absolute(relative)) {
        return NULL;
    }
    gchar *candidate = g_build_filename(workspace->root, relative, NULL);
    gchar *resolved = realpath(candidate, NULL);
    g_free(candidate);
    if (resolved == NULL || !path_inside_root(workspace, resolved) ||
        !g_file_test(resolved, G_FILE_TEST_IS_REGULAR)) {
        free(resolved);
        return NULL;
    }
    return resolved;
}

static gchar *safe_writable_file(const Workspace *workspace, const gchar *relative,
                                 struct stat *info) {
    if (relative == NULL || *relative == '\0' || g_path_is_absolute(relative)) {
        return NULL;
    }
    gchar *candidate = g_build_filename(workspace->root, relative, NULL);
    struct stat link_info;
    if (g_lstat(candidate, &link_info) != 0 || !S_ISREG(link_info.st_mode) ||
        S_ISLNK(link_info.st_mode)) {
        g_free(candidate);
        return NULL;
    }
    gchar *resolved = realpath(candidate, NULL);
    if (resolved == NULL || !path_inside_root(workspace, resolved) ||
        g_strcmp0(candidate, resolved) != 0 || stat(resolved, info) != 0 ||
        !S_ISREG(info->st_mode)) {
        g_free(candidate);
        free(resolved);
        return NULL;
    }
    g_free(candidate);
    return resolved;
}

static gboolean write_fd_all(int fd, const gchar *data, gsize length) {
    gsize written = 0;
    while (written < length) {
        ssize_t count = write(fd, data + written, length - written);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count <= 0) {
            return FALSE;
        }
        written += (gsize)count;
    }
    return TRUE;
}

static gboolean atomic_save_text(const Workspace *workspace, const gchar *relative,
                                 const gchar *text, gsize length, gchar **error_text) {
    *error_text = NULL;
    if (length > MAX_FILE_BYTES || memchr(text, '\0', length) != NULL ||
        !g_utf8_validate(text, (gssize)length, NULL)) {
        *error_text = g_strdup("save accepts only valid UTF-8 text without NUL and at most 4 MiB");
        return FALSE;
    }
    struct stat info;
    gchar *path = safe_writable_file(workspace, relative, &info);
    if (path == NULL) {
        *error_text = g_strdup("refused non-regular, symlinked, or out-of-workspace file");
        return FALSE;
    }
    gchar *directory = g_path_get_dirname(path);
    gchar *basename = g_path_get_basename(path);
    gchar *template_path = g_build_filename(directory, ".pocket-rocket-XXXXXX", NULL);
    int temporary = g_mkstemp(template_path);
    if (temporary < 0) {
        *error_text = g_strdup_printf("temporary file: %s", g_strerror(errno));
        g_free(directory);
        g_free(basename);
        g_free(template_path);
        free(path);
        return FALSE;
    }
    gboolean ok = fchmod(temporary, info.st_mode & 07777U) == 0 &&
                  write_fd_all(temporary, text, length) && fsync(temporary) == 0;
    int saved_errno = errno;
    if (close(temporary) != 0 && ok) {
        ok = FALSE;
        saved_errno = errno;
    }
    struct stat current;
    if (ok && (g_lstat(path, &current) != 0 || S_ISLNK(current.st_mode) ||
               current.st_dev != info.st_dev || current.st_ino != info.st_ino)) {
        ok = FALSE;
        saved_errno = ESTALE;
    }
    gboolean renamed = FALSE;
    if (ok && rename(template_path, path) != 0) {
        ok = FALSE;
        saved_errno = errno;
    } else if (ok) {
        renamed = TRUE;
    }
    if (ok) {
        int directory_fd = open(directory, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        if (directory_fd < 0 || fsync(directory_fd) != 0) {
            ok = FALSE;
            saved_errno = errno;
        }
        if (directory_fd >= 0) {
            (void)close(directory_fd);
        }
    }
    if (!ok && !renamed) {
        (void)unlink(template_path);
        *error_text = g_strdup_printf("atomic save failed for %s: %s", basename,
                                      g_strerror(saved_errno));
    } else if (!ok) {
        *error_text = g_strdup_printf("file replaced atomically, but directory durability sync failed for %s: %s",
                                      basename, g_strerror(saved_errno));
    }
    g_free(directory);
    g_free(basename);
    g_free(template_path);
    free(path);
    return ok;
}

static gboolean ignored_directory(const gchar *name) {
    return g_strcmp0(name, ".git") == 0 || g_strcmp0(name, "models") == 0 ||
           g_strcmp0(name, "runtime") == 0 || g_strcmp0(name, "var") == 0 ||
           g_strcmp0(name, "__pycache__") == 0;
}

static void collect_files(const gchar *absolute, const gchar *relative,
                          guint depth, GPtrArray *files) {
    if (depth > 20U || files->len >= MAX_FILES) {
        return;
    }
    GDir *directory = g_dir_open(absolute, 0, NULL);
    if (directory == NULL) {
        return;
    }
    const gchar *name;
    while ((name = g_dir_read_name(directory)) != NULL && files->len < MAX_FILES) {
        if (name[0] == '.' || ignored_directory(name)) {
            continue;
        }
        gchar *child_abs = g_build_filename(absolute, name, NULL);
        gchar *child_rel = relative[0] == '\0' ? g_strdup(name) :
                           g_build_filename(relative, name, NULL);
        struct stat info;
        if (g_lstat(child_abs, &info) != 0 || S_ISLNK(info.st_mode)) {
            g_free(child_abs);
            g_free(child_rel);
            continue;
        }
        if (S_ISDIR(info.st_mode)) {
            collect_files(child_abs, child_rel, depth + 1U, files);
        } else if (S_ISREG(info.st_mode)) {
            g_ptr_array_add(files, child_rel);
            child_rel = NULL;
        }
        g_free(child_abs);
        g_free(child_rel);
    }
    g_dir_close(directory);
}

static gint compare_paths(gconstpointer left, gconstpointer right) {
    return g_ascii_strcasecmp(*(const gchar *const *)left, *(const gchar *const *)right);
}

static void clear_file_list(Workspace *workspace) {
    GtkWidget *child = gtk_widget_get_first_child(GTK_WIDGET(workspace->files));
    while (child != NULL) {
        GtkWidget *next = gtk_widget_get_next_sibling(child);
        gtk_list_box_remove(workspace->files, GTK_LIST_BOX_ROW(child));
        child = next;
    }
}

static void open_selected(Workspace *workspace, const gchar *relative) {
    gchar *path = safe_existing_file(workspace, relative);
    if (path == NULL) {
        set_status(workspace, "Refused path outside workspace");
        return;
    }
    gchar *contents = NULL;
    gsize length = 0;
    GError *error = NULL;
    gboolean loaded = g_file_get_contents(path, &contents, &length, &error);
    if (!loaded || length > MAX_FILE_BYTES || memchr(contents, '\0', length) != NULL ||
        !g_utf8_validate(contents, (gssize)length, NULL)) {
        set_status(workspace, "File is unreadable, binary, or exceeds 4 MiB editor limit");
        if (error != NULL) {
            g_error_free(error);
        }
        g_free(contents);
        free(path);
        return;
    }
    gtk_text_buffer_set_text(workspace->editor, contents, (gint)length);
    g_free(workspace->selected);
    workspace->selected = g_strdup(relative);
    gchar *message = g_strdup_printf("Opened %s", relative);
    set_status(workspace, message);
    g_free(message);
    g_free(contents);
    free(path);
}

static void file_row_activated(GtkListBox *list, GtkListBoxRow *row, gpointer data) {
    (void)list;
    Workspace *workspace = data;
    const gchar *relative = g_object_get_data(G_OBJECT(row), "relative-path");
    open_selected(workspace, relative);
}

static void on_save(GtkButton *button, gpointer data) {
    (void)button;
    Workspace *workspace = data;
    if (!gtk_check_button_get_active(workspace->save_confirm)) {
        set_status(workspace, "Enable Confirm save before writing the selected file");
        return;
    }
    if (workspace->selected == NULL) {
        set_status(workspace, "Select a regular text file before saving");
        return;
    }
    GtkTextIter start;
    GtkTextIter end;
    gtk_text_buffer_get_bounds(workspace->editor, &start, &end);
    gchar *text = gtk_text_buffer_get_text(workspace->editor, &start, &end, FALSE);
    gsize length = strlen(text);
    gchar *error = NULL;
    gboolean ok = atomic_save_text(workspace, workspace->selected, text, length, &error);
    if (ok) {
        output_line(workspace, "save", workspace->selected);
        set_status(workspace, "Saved atomically; mode preserved");
        gtk_check_button_set_active(workspace->save_confirm, FALSE);
    } else {
        output_line(workspace, "save refused", error);
        set_status(workspace, "Save refused");
    }
    g_free(error);
    g_free(text);
}

static void refresh_files(Workspace *workspace) {
    clear_file_list(workspace);
    GPtrArray *files = g_ptr_array_new_with_free_func(g_free);
    collect_files(workspace->root, "", 0U, files);
    g_ptr_array_sort(files, compare_paths);
    for (guint i = 0; i < files->len; i++) {
        const gchar *relative = g_ptr_array_index(files, i);
        GtkListBoxRow *row = GTK_LIST_BOX_ROW(gtk_list_box_row_new());
        GtkWidget *label = gtk_label_new(relative);
        gtk_label_set_xalign(GTK_LABEL(label), 0.0F);
        gtk_widget_set_margin_start(label, 10);
        gtk_widget_set_margin_end(label, 10);
        gtk_widget_set_margin_top(label, 4);
        gtk_widget_set_margin_bottom(label, 4);
        gtk_list_box_row_set_child(row, label);
        g_object_set_data_full(G_OBJECT(row), "relative-path", g_strdup(relative), g_free);
        gtk_list_box_append(workspace->files, GTK_WIDGET(row));
    }
    g_ptr_array_free(files, TRUE);
    set_status(workspace, "Workspace file tree refreshed");
}

static void on_refresh(GtkButton *button, gpointer data) {
    (void)button;
    refresh_files(data);
}

static gboolean write_task(Workspace *workspace, const gchar *task) {
    if (task == NULL || *task == '\0') {
        set_status(workspace, "Enter a task before recording it");
        return FALSE;
    }
    gchar *path = g_build_filename(workspace->root, "ui", "tasks.log", NULL);
    gchar *old = NULL;
    gsize old_len = 0;
    GError *error = NULL;
    (void)g_file_get_contents(path, &old, &old_len, NULL);
    gchar *line = g_strdup_printf("%s\n", task);
    gchar *combined = g_strconcat(old != NULL ? old : "", line, NULL);
    gboolean ok = g_file_set_contents(path, combined, -1, &error);
    if (!ok) {
        gchar *message = g_strdup_printf("Task write failed: %s", error != NULL ? error->message : "unknown error");
        set_status(workspace, message);
        g_free(message);
        if (error != NULL) {
            g_error_free(error);
        }
    } else {
        output_line(workspace, "task recorded", task);
        set_status(workspace, "Task recorded in ui/tasks.log");
    }
    g_free(path);
    g_free(old);
    g_free(line);
    g_free(combined);
    return ok;
}

static void on_record_task(GtkButton *button, gpointer data) {
    (void)button;
    Workspace *workspace = data;
    const gchar *task = gtk_editable_get_text(GTK_EDITABLE(workspace->task));
    if (write_task(workspace, task)) {
        gtk_editable_set_text(GTK_EDITABLE(workspace->task), "");
    }
}

static gboolean write_all(int fd, const gchar *data, gsize length) {
    gsize written = 0;
    while (written < length) {
        ssize_t count = send(fd, data + written, length - written, MSG_NOSIGNAL);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count <= 0) {
            return FALSE;
        }
        written += (gsize)count;
    }
    return TRUE;
}

static gboolean post_local_json(guint16 port, const gchar *path, const gchar *json,
                                gchar **response, gint *http_status, gchar **error_text) {
    *response = NULL;
    *http_status = 0;
    *error_text = NULL;
    int fd = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) {
        *error_text = g_strdup_printf("socket: %s", g_strerror(errno));
        return FALSE;
    }
    struct timeval timeout = { .tv_sec = 20, .tv_usec = 0 };
    (void)setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    (void)setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    struct sockaddr_in address = {0};
    address.sin_family = AF_INET;
    address.sin_port = htons(port);
    (void)inet_pton(AF_INET, "127.0.0.1", &address.sin_addr);
    if (connect(fd, (struct sockaddr *)&address, sizeof(address)) != 0) {
        *error_text = g_strdup_printf("connect 127.0.0.1:%u: %s", port, g_strerror(errno));
        close(fd);
        return FALSE;
    }
    gchar *request = g_strdup_printf("POST %s HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: %zu\r\nConnection: close\r\n\r\n%s", path, strlen(json), json);
    gboolean sent = write_all(fd, request, strlen(request));
    g_free(request);
    if (!sent) {
        *error_text = g_strdup("send failed");
        close(fd);
        return FALSE;
    }
    GByteArray *bytes = g_byte_array_new();
    gchar buffer[8192];
    while (bytes->len < MAX_COMMAND_BYTES) {
        ssize_t count = recv(fd, buffer, sizeof(buffer), 0);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count <= 0) {
            break;
        }
        g_byte_array_append(bytes, (const guint8 *)buffer, (guint)count);
    }
    close(fd);
    g_byte_array_append(bytes, (const guint8 *)"", 1U);
    gchar *raw = (gchar *)bytes->data;
    gchar *header_end = strstr(raw, "\r\n\r\n");
    if (header_end == NULL) {
        *error_text = g_strdup("invalid HTTP response");
        g_byte_array_free(bytes, TRUE);
        return FALSE;
    }
    if (sscanf(raw, "HTTP/%*u.%*u %d", http_status) != 1) {
        *error_text = g_strdup("invalid HTTP status");
        g_byte_array_free(bytes, TRUE);
        return FALSE;
    }
    *response = g_strdup(header_end + 4);
    g_byte_array_free(bytes, TRUE);
    return TRUE;
}

static gchar *json_escape(const gchar *text) {
    GString *escaped = g_string_new("\"");
    for (const guchar *cursor = (const guchar *)text; cursor != NULL && *cursor != '\0'; cursor++) {
        switch (*cursor) {
        case '"': g_string_append(escaped, "\\\""); break;
        case '\\': g_string_append(escaped, "\\\\"); break;
        case '\n': g_string_append(escaped, "\\n"); break;
        case '\r': g_string_append(escaped, "\\r"); break;
        case '\t': g_string_append(escaped, "\\t"); break;
        default:
            if (*cursor < 0x20U) {
                g_string_append_printf(escaped, "\\u%04x", *cursor);
            } else {
                g_string_append_c(escaped, (gchar)*cursor);
            }
        }
    }
    g_string_append_c(escaped, '"');
    return g_string_free(escaped, FALSE);
}

static gboolean ask_done(gpointer user_data) {
    AskResult *result = user_data;
    Workspace *workspace = result->workspace;
    if (result->ok) {
        output_line(workspace, "local /ask", result->response);
        gchar *message = g_strdup_printf("/ask returned HTTP %d", result->status);
        set_status(workspace, message);
        g_free(message);
    } else {
        output_line(workspace, "local /ask error", result->error);
        set_status(workspace, "Local /ask failed");
    }
    g_free(result->error);
    g_free(result->response);
    g_free(result->prompt);
    g_free(result);
    return G_SOURCE_REMOVE;
}

static gpointer ask_worker(gpointer data) {
    AskJob *job = data;
    AskResult *result = g_new0(AskResult, 1);
    result->workspace = job->workspace;
    result->prompt = g_strdup(job->prompt);
    gchar *quoted = json_escape(job->prompt);
    gchar *request = g_strdup_printf("{\"question\":%s}", quoted);
    result->ok = post_local_json(job->port, "/ask", request, &result->response,
                                 &result->status, &result->error);
    g_free(request);
    g_free(quoted);
    g_free(job->prompt);
    g_free(job);
    g_main_context_invoke(NULL, ask_done, result);
    return NULL;
}

static void on_ask(GtkButton *button, gpointer data) {
    (void)button;
    Workspace *workspace = data;
    const gchar *prompt = gtk_editable_get_text(GTK_EDITABLE(workspace->prompt));
    if (prompt == NULL || *prompt == '\0') {
        set_status(workspace, "Enter a prompt for the local /ask endpoint");
        return;
    }
    AskJob *job = g_new0(AskJob, 1);
    job->workspace = workspace;
    job->prompt = g_strdup(prompt);
    job->port = (guint16)gtk_spin_button_get_value_as_int(workspace->port);
    set_status(workspace, "Calling loopback /ask…");
    GThread *thread = g_thread_new("local-ask", ask_worker, job);
    g_thread_unref(thread);
}

static gboolean reset_done(gpointer data) {
    ResetJob *job = data;
    Workspace *workspace = job->workspace;
    if (job->ok) {
        output_line(workspace, "local /reset", job->response);
        set_status(workspace, "Ephemeral session reset");
    } else {
        output_line(workspace, "local /reset error", job->error);
        set_status(workspace, "Local /reset failed");
    }
    g_free(job->error);
    g_free(job->response);
    g_free(job);
    return G_SOURCE_REMOVE;
}

static gpointer reset_worker(gpointer data) {
    ResetJob *job = data;
    job->ok = post_local_json(job->port, "/reset", "{}", &job->response,
                              &job->status, &job->error);
    g_main_context_invoke(NULL, reset_done, job);
    return NULL;
}

static void on_reset(GtkButton *button, gpointer data) {
    (void)button;
    Workspace *workspace = data;
    ResetJob *job = g_new0(ResetJob, 1);
    job->workspace = workspace;
    job->port = (guint16)gtk_spin_button_get_value_as_int(workspace->port);
    set_status(workspace, "Calling loopback /reset…");
    GThread *thread = g_thread_new("local-reset", reset_worker, job);
    g_thread_unref(thread);
}

static gboolean run_argv_capture(const gchar *root, gchar *const argv[], gchar **text,
                                 gint *exit_status) {
    *text = NULL;
    *exit_status = -1;
    int pipe_fds[2];
    if (pipe(pipe_fds) != 0) {
        *text = g_strdup_printf("pipe: %s", g_strerror(errno));
        return FALSE;
    }
    pid_t child = fork();
    if (child == 0) {
        (void)dup2(pipe_fds[1], STDOUT_FILENO);
        (void)dup2(pipe_fds[1], STDERR_FILENO);
        close(pipe_fds[0]);
        close(pipe_fds[1]);
        if (chdir(root) != 0) {
            _exit(126);
        }
        execvp(argv[0], argv);
        _exit(127);
    }
    close(pipe_fds[1]);
    if (child < 0) {
        close(pipe_fds[0]);
        *text = g_strdup_printf("fork: %s", g_strerror(errno));
        return FALSE;
    }
    GString *captured = g_string_new(NULL);
    gchar buffer[8192];
    ssize_t count;
    while ((count = read(pipe_fds[0], buffer, sizeof(buffer))) > 0 && captured->len < MAX_COMMAND_BYTES) {
        gsize keep = MIN((gsize)count, MAX_COMMAND_BYTES - captured->len);
        g_string_append_len(captured, buffer, (gssize)keep);
    }
    close(pipe_fds[0]);
    int status;
    if (waitpid(child, &status, 0) < 0) {
        g_string_append_printf(captured, "\nwaitpid: %s", g_strerror(errno));
        *text = g_string_free(captured, FALSE);
        return FALSE;
    }
    *exit_status = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
    *text = g_string_free(captured, FALSE);
    return TRUE;
}

static void command_result_free(CommandResult *result) {
    g_free(result->label);
    g_free(result->text);
    g_free(result);
}

static gboolean command_done(gpointer data) {
    CommandResult *result = data;
    Workspace *workspace = result->workspace;
    output_line(workspace, result->label, result->text);
    gchar *message = g_strdup_printf("%s exited %d", result->label, result->exit_status);
    set_status(workspace, message);
    g_free(message);
    command_result_free(result);
    return G_SOURCE_REMOVE;
}

typedef struct {
    CommandResult *result;
    gchar **argv;
} CommandJob;

static gpointer command_worker(gpointer data) {
    CommandJob *job = data;
    (void)run_argv_capture(job->result->workspace->root, job->argv,
                           &job->result->text, &job->result->exit_status);
    g_strfreev(job->argv);
    g_main_context_invoke(NULL, command_done, job->result);
    g_free(job);
    return NULL;
}

static void start_command(Workspace *workspace, const gchar *label,
                          const gchar *const *argv) {
    CommandJob *job = g_new0(CommandJob, 1);
    job->result = g_new0(CommandResult, 1);
    job->result->workspace = workspace;
    job->result->label = g_strdup(label);
    job->argv = g_strdupv((gchar **)argv);
    set_status(workspace, "Running local workspace command…");
    GThread *thread = g_thread_new("workspace-command", command_worker, job);
    g_thread_unref(thread);
}

static void on_git_status(GtkButton *button, gpointer data) {
    (void)button;
    static const gchar *const argv[] = {"git", "status", "--short", "--branch", NULL};
    start_command(data, "git status", argv);
}

static gboolean require_selected(Workspace *workspace) {
    if (workspace->selected == NULL || *workspace->selected == '\0') {
        set_status(workspace, "Select a repository file first");
        return FALSE;
    }
    return TRUE;
}

static void on_git_stage(GtkButton *button, gpointer data) {
    (void)button;
    Workspace *workspace = data;
    if (!require_selected(workspace)) {
        return;
    }
    const gchar *argv[] = {"git", "add", "--", workspace->selected, NULL};
    start_command(workspace, "git add selected", argv);
}

static void on_git_unstage(GtkButton *button, gpointer data) {
    (void)button;
    Workspace *workspace = data;
    if (!require_selected(workspace)) {
        return;
    }
    const gchar *argv[] = {"git", "restore", "--staged", "--", workspace->selected, NULL};
    start_command(workspace, "git restore --staged selected", argv);
}

static void on_git_commit(GtkButton *button, gpointer data) {
    (void)button;
    Workspace *workspace = data;
    if (!gtk_check_button_get_active(workspace->commit_confirm)) {
        set_status(workspace, "Enable Confirm commit before creating a commit");
        return;
    }
    const gchar *message = gtk_editable_get_text(GTK_EDITABLE(workspace->commit_message));
    if (message == NULL || *message == '\0' || strlen(message) > 512U) {
        set_status(workspace, "Commit message must be 1–512 characters");
        return;
    }
    const gchar *argv[] = {"git", "commit", "-m", message, NULL};
    start_command(workspace, "git commit staged changes", argv);
    gtk_check_button_set_active(workspace->commit_confirm, FALSE);
}

static void on_git_diff(GtkButton *button, gpointer data) {
    (void)button;
    static const gchar *const argv[] = {"git", "diff", "--stat", "--", NULL};
    start_command(data, "git diff --stat", argv);
}

static void on_make_test(GtkButton *button, gpointer data) {
    (void)button;
    static const gchar *const argv[] = {"make", "test", NULL};
    start_command(data, "make test", argv);
}

static void on_open_docs(GtkButton *button, gpointer data) {
    (void)button;
    Workspace *workspace = data;
    open_selected(workspace, "docs/GTK_WORKSPACE.md");
}

static void on_clear_output(GtkButton *button, gpointer data) {
    (void)button;
    Workspace *workspace = data;
    gtk_text_buffer_set_text(workspace->output, "", 0);
    set_status(workspace, "Output cleared");
}

static GtkWidget *scrolled(GtkWidget *child) {
    GtkWidget *scroll = gtk_scrolled_window_new();
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scroll), GTK_POLICY_AUTOMATIC, GTK_POLICY_AUTOMATIC);
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scroll), child);
    return scroll;
}

static GtkWidget *make_text_view(GtkTextBuffer **buffer, gboolean editable) {
    GtkWidget *view = gtk_text_view_new();
    *buffer = gtk_text_view_get_buffer(GTK_TEXT_VIEW(view));
    gtk_text_view_set_editable(GTK_TEXT_VIEW(view), editable);
    gtk_text_view_set_cursor_visible(GTK_TEXT_VIEW(view), editable);
    gtk_text_view_set_monospace(GTK_TEXT_VIEW(view), TRUE);
    gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(view), GTK_WRAP_WORD_CHAR);
    return view;
}

static void apply_css(void) {
    GtkCssProvider *provider = gtk_css_provider_new();
    gtk_css_provider_load_from_data(provider,
        "window { background: #111318; }"
        ".panel { background: #171a21; border: 1px solid #2a2f3a; }"
        ".title { color: #e6e9ef; font-weight: 700; }"
        ".muted { color: #8b93a3; }"
        "textview { background: #101217; color: #dbe1ea; }"
        "entry { background: #1c2029; color: #e6e9ef; }"
        "button.suggested-action { background: #5d5ce2; color: white; }", -1);
    gtk_style_context_add_provider_for_display(gdk_display_get_default(),
        GTK_STYLE_PROVIDER(provider), GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
    g_object_unref(provider);
}

static void activate(GtkApplication *application, gpointer data) {
    Workspace *workspace = data;
    workspace->application = application;
    apply_css();
    workspace->window = GTK_WINDOW(gtk_application_window_new(application));
    gtk_window_set_title(workspace->window, "Pocket Rocket Workspace");
    gtk_window_set_default_size(workspace->window, 1280, 800);

    GtkWidget *root_box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_window_set_child(workspace->window, root_box);
    GtkWidget *header = gtk_header_bar_new();
    GtkWidget *title = gtk_label_new("Pocket Rocket  ·  local workspace");
    gtk_widget_add_css_class(title, "title");
    gtk_header_bar_set_title_widget(GTK_HEADER_BAR(header), title);
    GtkWidget *refresh = gtk_button_new_with_label("Refresh");
    g_signal_connect(refresh, "clicked", G_CALLBACK(on_refresh), workspace);
    gtk_header_bar_pack_start(GTK_HEADER_BAR(header), refresh);
    GtkWidget *docs = gtk_button_new_with_label("Docs");
    g_signal_connect(docs, "clicked", G_CALLBACK(on_open_docs), workspace);
    gtk_header_bar_pack_start(GTK_HEADER_BAR(header), docs);
    GtkWidget *status_button = gtk_button_new_with_label("Git status");
    g_signal_connect(status_button, "clicked", G_CALLBACK(on_git_status), workspace);
    gtk_header_bar_pack_end(GTK_HEADER_BAR(header), status_button);
    GtkWidget *diff_button = gtk_button_new_with_label("Diff");
    g_signal_connect(diff_button, "clicked", G_CALLBACK(on_git_diff), workspace);
    gtk_header_bar_pack_end(GTK_HEADER_BAR(header), diff_button);
    GtkWidget *stage_button = gtk_button_new_with_label("Stage");
    g_signal_connect(stage_button, "clicked", G_CALLBACK(on_git_stage), workspace);
    gtk_header_bar_pack_end(GTK_HEADER_BAR(header), stage_button);
    GtkWidget *unstage_button = gtk_button_new_with_label("Unstage");
    g_signal_connect(unstage_button, "clicked", G_CALLBACK(on_git_unstage), workspace);
    gtk_header_bar_pack_end(GTK_HEADER_BAR(header), unstage_button);
    gtk_box_append(GTK_BOX(root_box), header);

    GtkWidget *main = gtk_paned_new(GTK_ORIENTATION_HORIZONTAL);
    gtk_widget_set_vexpand(main, TRUE);
    gtk_box_append(GTK_BOX(root_box), main);

    GtkWidget *left = gtk_box_new(GTK_ORIENTATION_VERTICAL, 8);
    gtk_widget_add_css_class(left, "panel");
    gtk_widget_set_size_request(left, 270, -1);
    GtkWidget *left_title = gtk_label_new("Repository files");
    gtk_label_set_xalign(GTK_LABEL(left_title), 0.0F);
    gtk_widget_set_margin_start(left_title, 12);
    gtk_widget_add_css_class(left_title, "muted");
    gtk_box_append(GTK_BOX(left), left_title);
    workspace->files = GTK_LIST_BOX(gtk_list_box_new());
    gtk_list_box_set_selection_mode(workspace->files, GTK_SELECTION_SINGLE);
    g_signal_connect(workspace->files, "row-activated", G_CALLBACK(file_row_activated), workspace);
    gtk_widget_set_vexpand(GTK_WIDGET(workspace->files), TRUE);
    gtk_box_append(GTK_BOX(left), scrolled(GTK_WIDGET(workspace->files)));
    gtk_paned_set_start_child(GTK_PANED(main), left);

    GtkWidget *center = gtk_box_new(GTK_ORIENTATION_VERTICAL, 8);
    gtk_widget_add_css_class(center, "panel");
    GtkWidget *editor_title = gtk_label_new("Source editor (guarded save)");
    gtk_label_set_xalign(GTK_LABEL(editor_title), 0.0F);
    gtk_widget_set_margin_start(editor_title, 12);
    gtk_widget_add_css_class(editor_title, "muted");
    gtk_box_append(GTK_BOX(center), editor_title);
    GtkWidget *editor_view = make_text_view(&workspace->editor, TRUE);
    gtk_widget_set_vexpand(editor_view, TRUE);
    gtk_box_append(GTK_BOX(center), scrolled(editor_view));
    gtk_paned_set_resize_start_child(GTK_PANED(main), TRUE);
    gtk_paned_set_shrink_start_child(GTK_PANED(main), FALSE);
    gtk_paned_set_end_child(GTK_PANED(main), center);
    gtk_paned_set_position(GTK_PANED(main), 270);

    GtkWidget *bottom = gtk_box_new(GTK_ORIENTATION_VERTICAL, 6);
    gtk_widget_set_size_request(bottom, -1, 240);
    GtkWidget *toolbar = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 6);
    workspace->save_confirm = GTK_CHECK_BUTTON(gtk_check_button_new_with_label("Confirm save"));
    gtk_widget_set_tooltip_text(GTK_WIDGET(workspace->save_confirm), "Required once for each file write");
    gtk_box_append(GTK_BOX(toolbar), GTK_WIDGET(workspace->save_confirm));
    GtkWidget *save = gtk_button_new_with_label("Save");
    g_signal_connect(save, "clicked", G_CALLBACK(on_save), workspace);
    gtk_box_append(GTK_BOX(toolbar), save);
    GtkWidget *prompt_label = gtk_label_new("Ask");
    gtk_box_append(GTK_BOX(toolbar), prompt_label);
    workspace->prompt = GTK_ENTRY(gtk_entry_new());
    gtk_entry_set_placeholder_text(workspace->prompt, "Prompt sent only to 127.0.0.1 /ask");
    gtk_widget_set_hexpand(GTK_WIDGET(workspace->prompt), TRUE);
    gtk_box_append(GTK_BOX(toolbar), GTK_WIDGET(workspace->prompt));
    workspace->port = GTK_SPIN_BUTTON(gtk_spin_button_new_with_range(1025, 65535, 1));
    gtk_spin_button_set_value(workspace->port, DEFAULT_PORT);
    gtk_widget_set_tooltip_text(GTK_WIDGET(workspace->port), "Loopback API port");
    gtk_box_append(GTK_BOX(toolbar), GTK_WIDGET(workspace->port));
    GtkWidget *ask = gtk_button_new_with_label("Ask local");
    gtk_widget_add_css_class(ask, "suggested-action");
    g_signal_connect(ask, "clicked", G_CALLBACK(on_ask), workspace);
    gtk_box_append(GTK_BOX(toolbar), ask);
    GtkWidget *reset = gtk_button_new_with_label("Reset");
    g_signal_connect(reset, "clicked", G_CALLBACK(on_reset), workspace);
    gtk_box_append(GTK_BOX(toolbar), reset);
    GtkWidget *test = gtk_button_new_with_label("Run tests");
    g_signal_connect(test, "clicked", G_CALLBACK(on_make_test), workspace);
    gtk_box_append(GTK_BOX(toolbar), test);
    GtkWidget *clear = gtk_button_new_with_label("Clear output");
    g_signal_connect(clear, "clicked", G_CALLBACK(on_clear_output), workspace);
    gtk_box_append(GTK_BOX(toolbar), clear);
    gtk_box_append(GTK_BOX(root_box), toolbar);

    GtkWidget *taskbar = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 6);
    GtkWidget *task_label = gtk_label_new("Task");
    gtk_box_append(GTK_BOX(taskbar), task_label);
    workspace->task = GTK_ENTRY(gtk_entry_new());
    gtk_entry_set_placeholder_text(workspace->task, "Record a local action in ui/tasks.log");
    gtk_widget_set_hexpand(GTK_WIDGET(workspace->task), TRUE);
    gtk_box_append(GTK_BOX(taskbar), GTK_WIDGET(workspace->task));
    GtkWidget *record = gtk_button_new_with_label("Record task");
    g_signal_connect(record, "clicked", G_CALLBACK(on_record_task), workspace);
    gtk_box_append(GTK_BOX(taskbar), record);
    workspace->commit_message = GTK_ENTRY(gtk_entry_new());
    gtk_entry_set_placeholder_text(workspace->commit_message, "Commit message for staged changes");
    gtk_widget_set_hexpand(GTK_WIDGET(workspace->commit_message), TRUE);
    gtk_box_append(GTK_BOX(taskbar), GTK_WIDGET(workspace->commit_message));
    workspace->commit_confirm = GTK_CHECK_BUTTON(gtk_check_button_new_with_label("Confirm commit"));
    gtk_box_append(GTK_BOX(taskbar), GTK_WIDGET(workspace->commit_confirm));
    GtkWidget *commit = gtk_button_new_with_label("Commit staged");
    g_signal_connect(commit, "clicked", G_CALLBACK(on_git_commit), workspace);
    gtk_box_append(GTK_BOX(taskbar), commit);
    gtk_box_append(GTK_BOX(root_box), taskbar);

    GtkWidget *output_view = make_text_view(&workspace->output, FALSE);
    gtk_widget_set_size_request(output_view, -1, 130);
    gtk_box_append(GTK_BOX(root_box), scrolled(output_view));
    workspace->status = GTK_LABEL(gtk_label_new("Starting…"));
    gtk_label_set_xalign(workspace->status, 0.0F);
    gtk_widget_add_css_class(GTK_WIDGET(workspace->status), "muted");
    gtk_widget_set_margin_start(GTK_WIDGET(workspace->status), 10);
    gtk_box_append(GTK_BOX(root_box), GTK_WIDGET(workspace->status));
    refresh_files(workspace);
    gtk_window_present(workspace->window);
}

static void workspace_free(Workspace *workspace) {
    g_free(workspace->root);
    g_free(workspace->selected);
    g_free(workspace);
}

int main(int argc, char **argv) {
    const gchar *root_arg = argc > 1 ? argv[1] : g_getenv("POCKET_ROCKET_WORKSPACE");
    if (root_arg == NULL || *root_arg == '\0') {
        g_printerr("usage: %s WORKSPACE_ROOT\n", argv[0]);
        return EXIT_FAILURE;
    }
    gchar *root = realpath(root_arg, NULL);
    if (root == NULL || !g_file_test(root, G_FILE_TEST_IS_DIR)) {
        g_printerr("workspace root is not a directory: %s\n", root_arg);
        free(root);
        return EXIT_FAILURE;
    }
    Workspace *workspace = g_new0(Workspace, 1);
    workspace->root = g_strdup(root);
    free(root);
    GtkApplication *application = gtk_application_new("local.pocketrocket.Workspace", G_APPLICATION_DEFAULT_FLAGS);
    g_signal_connect(application, "activate", G_CALLBACK(activate), workspace);
    int result = g_application_run(G_APPLICATION(application), argc, argv);
    g_object_unref(application);
    workspace_free(workspace);
    return result;
}
