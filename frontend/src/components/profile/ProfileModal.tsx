import { useEffect, useState } from "react";
import { Loader2, Save, KeyRound, LogOut, AlertTriangle } from "lucide-react";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "../ui/dialog";
import { Button } from "../ui/button";
import { api } from "../../api/endpoints";
import type { User } from "../../types/api";

interface ProfileModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: User | null;
  onLogout: () => void;
  onAccountDeleted: () => void;
  onUpdated?: () => void;
}

type Tab = "info" | "password";

export function ProfileModal({ open, onOpenChange, user, onLogout, onAccountDeleted, onUpdated }: ProfileModalProps) {
  const [tab, setTab] = useState<Tab>("info");
  const [displayName, setDisplayName] = useState("");
  const [savingName, setSavingName] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [nameSuccess, setNameSuccess] = useState(false);

  // 修改密码
  const [oldPwd, setOldPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [changing, setChanging] = useState(false);
  const [pwdError, setPwdError] = useState<string | null>(null);
  const [pwdSuccess, setPwdSuccess] = useState(false);

  // 删除账号
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (open && user) {
      setDisplayName(user.display_name || "");
      setTab("info");
      setNameError(null);
      setNameSuccess(false);
      setPwdError(null);
      setPwdSuccess(false);
      setOldPwd("");
      setNewPwd("");
      setConfirmPwd("");
      setDeleteConfirm(false);
    }
  }, [open, user]);

  async function handleSaveName() {
    if (!user) return;
    setNameError(null);
    setNameSuccess(false);
    const trimmed = displayName.trim();
    if (trimmed.length > 64) {
      setNameError("昵称最多 64 个字符");
      return;
    }
    setSavingName(true);
    try {
      const updated = await api.updateProfile({ display_name: trimmed || null });
      setDisplayName(updated.display_name || "");
      setNameSuccess(true);
      onUpdated?.();
      setTimeout(() => setNameSuccess(false), 2000);
    } catch (err: any) {
      setNameError(err?.message || "保存失败");
    } finally {
      setSavingName(false);
    }
  }

  async function handleChangePassword() {
    if (!user) return;
    setPwdError(null);
    setPwdSuccess(false);
    if (!oldPwd || !newPwd || !confirmPwd) {
      setPwdError("请填写全部字段");
      return;
    }
    if (newPwd.length < 6) {
      setPwdError("新密码至少 6 位");
      return;
    }
    if (newPwd !== confirmPwd) {
      setPwdError("两次输入的新密码不一致");
      return;
    }
    if (newPwd === oldPwd) {
      setPwdError("新密码不能与旧密码相同");
      return;
    }
    setChanging(true);
    try {
      await api.changePassword({ old_password: oldPwd, new_password: newPwd });
      setPwdSuccess(true);
      setOldPwd("");
      setNewPwd("");
      setConfirmPwd("");
      setTimeout(() => setPwdSuccess(false), 2500);
    } catch (err: any) {
      setPwdError(err?.message || "修改密码失败");
    } finally {
      setChanging(false);
    }
  }

  async function handleDeleteAccount() {
    if (!deleteConfirm) return;
    setDeleting(true);
    try {
      await api.deleteAccount();
      onAccountDeleted();
    } catch (err: any) {
      // 删除失败也会回到登录态，但不会调用 onAccountDeleted
      setDeleteConfirm(false);
      setDeleting(false);
      alert(err?.message || "删除账号失败");
    }
  }

  if (!user) {
    return null;
  }

  const initialChar = (user.display_name || user.username).charAt(0).toUpperCase();
  const avatarGradient = "bg-gradient-to-br from-blue-500 to-purple-500";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg p-0">
        <DialogTitle className="sr-only">个人中心</DialogTitle>
        <DialogDescription className="sr-only">查看和修改你的个人信息</DialogDescription>

        {/* 头部 */}
        <div className="flex items-center gap-4 border-b border-neutral-200 px-6 py-5 dark:border-neutral-700">
          <div className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-full text-xl font-semibold text-white ${avatarGradient}`}>
            {initialChar}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-lg font-semibold text-neutral-900 dark:text-neutral-100">
              {user.display_name || user.username}
            </div>
            <div className="truncate text-sm text-neutral-500">@{user.username}</div>
            <div className="mt-1 text-xs text-neutral-400">
              注册于 {new Date(user.created_at).toLocaleDateString("zh-CN")}
              {user.last_login_at && <> · 上次登录 {new Date(user.last_login_at).toLocaleString("zh-CN")}</>}
            </div>
          </div>
        </div>

        {/* Tab */}
        <div className="flex gap-1 border-b border-neutral-200 px-6 pt-2 dark:border-neutral-700">
          {(["info", "password"] as const).map((t) => (
            <button
              key={t}
              onClick={() => { setTab(t); setNameError(null); setPwdError(null); }}
              className={`px-3 py-2.5 text-sm font-medium transition-colors border-b-2 ${
                tab === t
                  ? "border-blue-600 text-blue-600 dark:text-blue-400 dark:border-blue-400"
                  : "border-transparent text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300"
              }`}
            >
              {t === "info" ? "基本信息" : "修改密码"}
            </button>
          ))}
        </div>

        <div className="px-6 py-5">
          {tab === "info" && (
            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-neutral-700 dark:text-neutral-300">
                  用户名
                </label>
                <input
                  type="text"
                  value={user.username}
                  disabled
                  className="h-10 w-full rounded-lg border border-neutral-200 bg-neutral-100 px-3 text-sm text-neutral-500 dark:border-neutral-700 dark:bg-neutral-800"
                />
                <p className="mt-1 text-xs text-neutral-400">用户名不可修改</p>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium text-neutral-700 dark:text-neutral-300">
                  昵称（显示名）
                </label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="输入昵称"
                  maxLength={64}
                  className="h-10 w-full rounded-lg border border-neutral-200 bg-white px-3 text-sm outline-none transition-colors placeholder:text-neutral-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-neutral-700 dark:bg-neutral-900"
                />
              </div>

              {nameError && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-400">
                  {nameError}
                </div>
              )}
              {nameSuccess && (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-900/20 dark:text-emerald-400">
                  保存成功
                </div>
              )}

              <Button onClick={handleSaveName} disabled={savingName} className="w-full">
                {savingName && <Loader2 className="h-4 w-4 animate-spin" />}
                <Save className="h-4 w-4" /> 保存昵称
              </Button>
            </div>
          )}

          {tab === "password" && (
            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-neutral-700 dark:text-neutral-300">
                  当前密码
                </label>
                <input
                  type="password"
                  value={oldPwd}
                  onChange={(e) => setOldPwd(e.target.value)}
                  className="h-10 w-full rounded-lg border border-neutral-200 bg-white px-3 text-sm outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-neutral-700 dark:bg-neutral-900"
                  autoComplete="current-password"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium text-neutral-700 dark:text-neutral-300">
                  新密码
                </label>
                <input
                  type="password"
                  value={newPwd}
                  onChange={(e) => setNewPwd(e.target.value)}
                  placeholder="至少 6 位"
                  className="h-10 w-full rounded-lg border border-neutral-200 bg-white px-3 text-sm outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-neutral-700 dark:bg-neutral-900"
                  autoComplete="new-password"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium text-neutral-700 dark:text-neutral-300">
                  确认新密码
                </label>
                <input
                  type="password"
                  value={confirmPwd}
                  onChange={(e) => setConfirmPwd(e.target.value)}
                  className="h-10 w-full rounded-lg border border-neutral-200 bg-white px-3 text-sm outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-neutral-700 dark:bg-neutral-900"
                  autoComplete="new-password"
                />
              </div>

              {pwdError && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-400">
                  {pwdError}
                </div>
              )}
              {pwdSuccess && (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-900/20 dark:text-emerald-400">
                  密码修改成功
                </div>
              )}

              <Button onClick={handleChangePassword} disabled={changing} className="w-full">
                {changing && <Loader2 className="h-4 w-4 animate-spin" />}
                <KeyRound className="h-4 w-4" /> 修改密码
              </Button>
            </div>
          )}
        </div>

        {/* 底部危险区 + 退出登录 */}
        <div className="border-t border-neutral-200 px-6 py-4 dark:border-neutral-700">
          {!deleteConfirm ? (
            <div className="flex items-center justify-between">
              <button
                onClick={onLogout}
                className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800"
              >
                <LogOut className="h-4 w-4" /> 退出登录
              </button>
              <button
                onClick={() => setDeleteConfirm(true)}
                className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
              >
                <AlertTriangle className="h-4 w-4" /> 删除账号
              </button>
            </div>
          ) : (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-900/50 dark:bg-red-900/20">
              <div className="flex items-center gap-2 text-sm font-medium text-red-700 dark:text-red-400">
                <AlertTriangle className="h-4 w-4" /> 确认删除账号？
              </div>
              <p className="mt-1 text-xs text-red-600 dark:text-red-400/80">
                你的所有会话和分析产物将被永久删除，无法恢复。
              </p>
              <div className="mt-3 flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setDeleteConfirm(false)} disabled={deleting}>
                  取消
                </Button>
                <Button variant="destructive" size="sm" onClick={handleDeleteAccount} disabled={deleting}>
                  {deleting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  确认删除
                </Button>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
