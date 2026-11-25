import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FolderKey, KeyRound, ShieldOff, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError, type Project, type ProjectRole, type Role, type User } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { formatIsoDate } from "@/lib/dates";
import { askConfirm } from "@/components/ConfirmDialog";

/**
 * The accounts that may open this admin area, and what each of them may do.
 *
 * Two things this panel is careful about, both of them about the person
 * using it rather than about security (the backend refuses all of it
 * anyway, and refusing it there is what makes it true):
 *
 * - Your own row can only do the one thing that has a use: STEP DOWN. That
 *   is a real handover ("make her an administrator, then make me an
 *   editor"), and the backend allows it for exactly as long as somebody
 *   else is left to administer the instance. It asks first, because the
 *   next thing that happens is being signed out. Deleting your own account
 *   and resetting your own password are not offered at all -- the first has
 *   no version that leaves you anywhere, and the second is what the Account
 *   panel is for, which asks for your current password.
 * - Every consequence is written next to the button that causes it: that
 *   lowering a role signs the person out, that a password reset does too,
 *   and that the last administrator cannot be removed. A confirm dialog
 *   that only says "are you sure?" asks a question the reader has no way to
 *   answer.
 */
export function AdminUsersCard({ onClose, onSelfChanged }: { onClose: () => void; onSelfChanged: () => void }) {
  const { t, lang: uiLang } = useI18n();
  const [users, setUsers] = useState<User[] | null>(null);
  const [roles, setRoles] = useState<Role[]>(["reader", "viewer", "editor", "admin"]);
  const [me, setMe] = useState("");
  const [minLength, setMinLength] = useState(8);
  const [newName, setNewName] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<Role>("viewer");
  const [busy, setBusy] = useState(false);
  // Permissions per project: which account's list is open, and the
  // projects to list in it.
  const [openProjects, setOpenProjects] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);

  async function load() {
    try {
      const result = await api.adminListUsers();
      setUsers(result.users);
      setRoles(result.roles);
      setMe(result.me);
      setMinLength(result.min_password_length);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
      setUsers([]);
    }
  }

  useEffect(() => {
    void load();
    api
      .adminListProjects()
      .then((r) => setProjects(r.projects))
      .catch(() => setProjects([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, on mount
  }, []);

  function fail(err: unknown) {
    toast.error(err instanceof ApiError ? err.message : t("common.error"));
  }

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api.adminCreateUser(newName, newPassword, newRole);
      toast.success(t("users.created").replace("{name}", newName.trim()));
      setNewName("");
      setNewPassword("");
      setNewRole("viewer");
      await load();
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function onRole(user: User, role: Role) {
    // Only for your own row, and only downwards: the request that follows
    // takes your own access away and signs you out, which is not something
    // to discover from the login screen.
    if (user.username === me && !(await askConfirm({ title: t("users.stepDownConfirm").replace("{role}", t(`users.role.${role}` as never)), danger: true }))) {
      await load();
      return;
    }
    try {
      await api.adminSetUserRole(user.username, role);
      toast.success(t("users.roleChanged").replace("{name}", user.username));
      await load();
      // The signed-in account's own role is what the surrounding UI decides
      // what to show by. It cannot be this row (own-row controls are not
      // rendered), but an admin count that just changed is worth a refresh
      // anyway -- and it costs one request.
      onSelfChanged();
    } catch (err) {
      fail(err);
    }
  }

  async function onProjectRole(user: User, slug: string, value: ProjectRole | "") {
    const next = { ...user.projects };
    if (value) next[slug] = value;
    else delete next[slug];
    try {
      await api.adminSetUserProjects(user.username, next);
      toast.success(t("users.projectsSaved").replace("{name}", user.username));
      await load();
    } catch (err) {
      fail(err);
    }
  }

  async function onResetPassword(user: User) {
    const password = prompt(t("users.passwordPrompt").replace("{name}", user.username), "");
    if (password === null) return;
    if (password.length < minLength) {
      toast.error(t("users.passwordTooShort").replace("{n}", String(minLength)));
      return;
    }
    try {
      const { sessions_ended } = await api.adminSetUserPassword(user.username, password);
      toast.success(t("users.passwordSet").replace("{name}", user.username).replace("{n}", String(sessions_ended)));
      await load();
    } catch (err) {
      fail(err);
    }
  }

  async function onResetMfa(user: User) {
    if (!(await askConfirm({ title: t("users.mfaResetConfirm").replace("{name}", user.username), danger: true }))) return;
    try {
      await api.adminResetUserMfa(user.username);
      toast.success(t("users.mfaReset").replace("{name}", user.username));
      await load();
    } catch (err) {
      fail(err);
    }
  }

  async function onDelete(user: User) {
    if (!(await askConfirm({ title: t("users.deleteConfirm").replace("{name}", user.username), confirmLabel: t("admin.delete"), danger: true }))) return;
    try {
      await api.adminDeleteUser(user.username);
      toast.success(t("users.deleted").replace("{name}", user.username));
      await load();
    } catch (err) {
      fail(err);
    }
  }

  return (
    <Card className="mb-4">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{t("users.title")}</CardTitle>
        <Button variant="ghost" size="sm" onClick={onClose}>
          {t("common.back")}
        </Button>
      </CardHeader>
      <CardContent>
        <p className="mb-3 text-sm text-[var(--muted)]">{t("users.intro")}</p>

        <dl className="mb-4 grid gap-1 text-xs text-[var(--muted)] sm:grid-cols-2 lg:grid-cols-4">
          {roles.map((role) => (
            <div key={role} className="rounded-lg border border-[var(--border)] px-2.5 py-1.5">
              <dt className="font-medium text-[var(--ink)]">{t(`users.role.${role}` as never)}</dt>
              <dd>{t(`users.roleHint.${role}` as never)}</dd>
            </div>
          ))}
        </dl>

        {users === null ? (
          <p className="text-sm text-[var(--muted)]">{t("common.loading")}</p>
        ) : (
          <div className="flex flex-col divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
            {users.map((user) => {
              const isMe = user.username === me;
              return (
                <div key={user.username} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
                  <span className="font-medium">{user.username}</span>
                  {isMe && <span className="text-xs text-[var(--muted)]">{t("users.you")}</span>}
                  <span className="flex-1 text-xs text-[var(--muted)]">
                    {user.last_login_at
                      ? t("users.lastLogin").replace("{date}", formatIsoDate(user.last_login_at.slice(0, 10), uiLang))
                      : t("users.neverSignedIn")}
                    {user.sessions > 0 && ` · ${t("users.sessions").replace("{n}", String(user.sessions))}`}
                    {user.mfa && ` · ${t("users.mfaOn")}`}
                    {Object.keys(user.projects ?? {}).length > 0 &&
                      ` · ${t("users.projectExceptions").replace("{n}", String(Object.keys(user.projects).length))}`}
                  </span>

                  {/* Permissions per project: only viewer and editor
                      accounts have any (backend services/project_access.py). */}
                  {(user.role === "viewer" || user.role === "editor") && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      aria-label={t("users.projects")}
                      aria-expanded={openProjects === user.username}
                      title={t("users.projects")}
                      onClick={() => setOpenProjects((o) => (o === user.username ? null : user.username))}
                    >
                      <FolderKey className="h-3.5 w-3.5" />
                    </Button>
                  )}

                  {/* The role is offered on every row, your own included --
                      stepping down is the one self-change with a use. What
                      your own row does NOT get is the two buttons beside
                      it. See the component docstring. */}
                  <select
                    value={user.role}
                    onChange={(e) => void onRole(user, e.target.value as Role)}
                    aria-label={t("users.role")}
                    className="h-8 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-xs"
                  >
                    {roles.map((role) => (
                      <option key={role} value={role}>
                        {t(`users.role.${role}` as never)}
                      </option>
                    ))}
                  </select>
                  {!isMe && (
                    <>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        aria-label={t("users.resetPassword")}
                        title={t("users.resetPassword")}
                        onClick={() => void onResetPassword(user)}
                      >
                        <KeyRound className="h-3.5 w-3.5" />
                      </Button>
                      {user.mfa && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          aria-label={t("users.mfaResetButton")}
                          title={t("users.mfaResetButton")}
                          onClick={() => void onResetMfa(user)}
                        >
                          <ShieldOff className="h-3.5 w-3.5" />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        aria-label={t("admin.delete")}
                        onClick={() => void onDelete(user)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </>
                  )}
                  {openProjects === user.username && (user.role === "viewer" || user.role === "editor") && (
                    <div className="basis-full rounded-lg bg-[var(--surface-2)] px-3 py-2">
                      <p className="mb-2 text-xs text-[var(--muted)]">
                        {t("users.projectsHint").replace("{role}", t(`users.role.${user.role}` as never))}
                      </p>
                      {projects.length === 0 && <p className="text-xs text-[var(--muted)]">{t("users.noProjects")}</p>}
                      <ul className="flex flex-col gap-1">
                        {projects.map((project) => (
                          <li key={project.slug} className="flex items-center gap-2 text-xs">
                            <span className="flex-1">{project.name}</span>
                            <select
                              value={user.projects?.[project.slug] ?? ""}
                              onChange={(e) => void onProjectRole(user, project.slug, e.target.value as ProjectRole | "")}
                              aria-label={t("users.projectRoleFor").replace("{project}", project.name)}
                              className="h-7 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-xs"
                            >
                              <option value="">
                                {t("users.projectAsRole").replace("{role}", t(`users.role.${user.role}` as never))}
                              </option>
                              {user.role !== "viewer" && <option value="viewer">{t("users.role.viewer")}</option>}
                              {user.role !== "editor" && <option value="editor">{t("users.role.editor")}</option>}
                            </select>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        <form onSubmit={onCreate} className="mt-3 flex flex-col gap-2 rounded-lg border border-[var(--border)] p-3">
          <span className="text-sm font-medium">{t("users.newTitle")}</span>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-1 flex-col gap-1 text-xs text-[var(--muted)]">
              {t("users.username")}
              <Input value={newName} onChange={(e) => setNewName(e.target.value)} required />
            </label>
            <label className="flex flex-1 flex-col gap-1 text-xs text-[var(--muted)]">
              {t("users.password")}
              <Input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                minLength={minLength}
                required
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
              {t("users.role")}
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as Role)}
                className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-sm"
              >
                {roles.map((role) => (
                  <option key={role} value={role}>
                    {t(`users.role.${role}` as never)}
                  </option>
                ))}
              </select>
            </label>
            <Button type="submit" disabled={busy}>
              {t("users.create")}
            </Button>
          </div>
          {/* The password is typed here and told to the person by whatever
              means the operator already uses. There is no invitation email:
              this app sends no mail, and pretending otherwise would be a
              feature that silently does nothing. */}
          <span className="text-xs text-[var(--muted)]">{t("users.newHint").replace("{n}", String(minLength))}</span>
        </form>
      </CardContent>
    </Card>
  );
}
