// Tiny native launcher: spawns the project's Python as a child so macOS attributes
// Microphone / Accessibility / Input Monitoring permissions to LocalFlow.app.
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <fcntl.h>
#include <unistd.h>
extern char **environ;
int main(void) {
    const char *root = PROJECT_ROOT;
    char py[1024], log[1024];
    snprintf(py, sizeof py, "%s/.venv/bin/python", root);
    snprintf(log, sizeof log, "%s/Library/Logs/LocalFlow.log", getenv("HOME"));
    chdir(root);
    setenv("PYTHONUNBUFFERED", "1", 1);
    posix_spawn_file_actions_t fa;
    posix_spawn_file_actions_init(&fa);
    posix_spawn_file_actions_addopen(&fa, 1, log, O_WRONLY | O_CREAT | O_APPEND, 0644);
    posix_spawn_file_actions_adddup2(&fa, 1, 2);
    char *argv[] = {py, "-m", "localflow", NULL};
    // Exit code 75 means "restart me" (e.g. a permission was just granted).
    for (int tries = 0; tries < 5; tries++) {
        pid_t pid;
        if (posix_spawn(&pid, py, &fa, NULL, argv, environ) != 0) { perror("spawn"); return 1; }
        int status; waitpid(pid, &status, 0);
        if (!WIFEXITED(status) || WEXITSTATUS(status) != 75) return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
        sleep(1);
    }
    return 0;
}
