import { useEffect, useState } from "react";
import { MessageSquarePlus, Plus, Trash2, X, Settings, LogOut, User as UserIcon } from "lucide-react";
import type { Session } from "../../types/api";
import { useChatStore } from "../../store/chatStore";
import { useAuthStore } from "../../store/authStore";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "../ui/dialog";
import { AuthModal } from "../auth/AuthModal";
import { ProfileModal } from "../profile/ProfileModal";
import { SettingsModal } from "../profile/SettingsModal";
import { api } from "../../api/endpoints";
import { useMe } from "../../queries";
import { cn } from "../../utils/format";

interface SidebarProps {
  sessions: Session[];
  onCreate: () => void;
  onDelete: (id: string) => void;
  creating: boolean;
}

export function Sidebar({ sessions, onCreate, onDelete, creating }: SidebarProps) {
  const currentId = useChatStore((state) => state.currentSessionId);
  const setCurrent = useChatStore((state) => state.setCurrentSession);
  const open = useChatStore((state) => state.sidebarOpen);
  const setOpen = useChatStore((state) => state.setSidebarOpen);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [logoutLoading, setLogoutLoading] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);

  const authModalOpen = useAuthStore((state) => state.authModalOpen);
  const openAuthModal = useAuthStore((state) => state.openAuthModal);
  const closeAuthModal = useAuthStore((state) => state.closeAuthModal);

  const profileModalOpen = useAuthStore((state) => state.profileModalOpen);
  const openProfileModal = useAuthStore((state) => state.openProfileModal);
  const closeProfileModal = useAuthStore((state) => state.closeProfileModal);

  const settingsModalOpen = useAuthStore((state) => state.settingsModalOpen);
  const openSettingsModal = useAuthStore((state) => state.openSettingsModal);
  const closeSettingsModal = useAuthStore((state) => state.closeSettingsModal);

  const { data: meData, refetch: refetchMe } = useMe();
  const user = meData?.user ?? null;

  // 同步到全局 auth store
  const setMe = useAuthStore((state) => state.setMe);
  useEffect(() => {
    if (meData) {
      setMe(meData.user, meData.anon_sessions_remaining, meData.anon_messages_remaining_per_session);
    }
  }, [meData, setMe]);

  async function handleLogout() {
    setLogoutLoading(true);
    setLogoutError(null);
    try {
      await api.logout();
      await refetchMe();
      setMenuOpen(false);
      closeProfileModal();
    } catch (err: any) {
      setLogoutError(err?.message || "登出失败");
    } finally {
      setLogoutLoading(false);
    }
  }

  const displayName = user?.display_name || user?.username || "访客";
  const initialChar = displayName.charAt(0).toUpperCase();
  const isAnonymous = !user;

  return (
    <>
      {open && (
        <button
          aria-label="关闭会话列表"
          className="fixed inset-0 z-30 bg-black/30 md:hidden"
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-72 shrink-0 flex-col border-r border-neutral-200 bg-neutral-50 transition-transform dark:border-neutral-800 dark:bg-neutral-950 md:static md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-16 items-center justify-between px-4">
          <div className="flex items-center gap-2 font-semibold">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-blue-600 text-white">D</span>
            数据分析 Agent
          </div>
          <Button variant="ghost" size="icon" className="md:hidden" aria-label="关闭侧栏" onClick={() => setOpen(false)}>
            <X className="h-5 w-5" />
          </Button>
        </div>
        <div className="px-3">
          <Button className="w-full" onClick={onCreate} disabled={creating}>
            <Plus className="h-4 w-4" />新建分析
          </Button>
        </div>
        <div className="mt-5 px-4 text-xs font-medium text-neutral-500">最近会话</div>
        <div className="mt-2 flex-1 space-y-1 overflow-y-auto px-3 pb-4">
          {sessions.map((session) => (
            <div
              key={session.id}
              className={cn(
                "group flex items-center rounded-lg",
                currentId === session.id && "bg-white shadow-sm dark:bg-neutral-900",
              )}
            >
              <button className="min-w-0 flex-1 px-3 py-2.5 text-left" onClick={() => setCurrent(session.id)}>
                <span className="block truncate text-sm">{session.title || "新分析"}</span>
                <span className="mt-0.5 block truncate text-xs text-neutral-500">
                  {session.summary || new Date(session.updated_at).toLocaleDateString("zh-CN")}
                </span>
              </button>
              <Button
                variant="ghost"
                size="icon"
                className="mr-1 h-8 w-8 text-neutral-400 opacity-100 md:opacity-0 md:group-hover:opacity-100"
                aria-label={`删除会话 ${session.title}`}
                onClick={() => setDeleteId(session.id)}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}
          {!sessions.length && (
            <div className="px-3 py-8 text-center text-sm text-neutral-500">
              <MessageSquarePlus className="mx-auto mb-2 h-6 w-6" />
              还没有分析会话
            </div>
          )}
        </div>

        {/* 底部用户卡片 */}
        <div className="border-t border-neutral-200 p-3 dark:border-neutral-800">
          <div className="relative">
            <button
              onClick={() => (isAnonymous ? openAuthModal() : setMenuOpen((v) => !v))}
              className={cn(
                "flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors",
                "hover:bg-neutral-200/70 dark:hover:bg-neutral-800",
              )}
            >
              {/* 头像 */}
              <div
                className={cn(
                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold text-white",
                  isAnonymous
                    ? "bg-neutral-400 dark:bg-neutral-600"
                    : "bg-gradient-to-br from-blue-500 to-purple-500",
                )}
              >
                {isAnonymous ? (
                  <UserIcon className="h-5 w-5" />
                ) : (
                  initialChar
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-neutral-900 dark:text-neutral-100">
                  {isAnonymous ? "未登录" : displayName}
                </div>
                <div className="truncate text-xs text-neutral-500">
                  {isAnonymous
                    ? `${meData?.anon_sessions_remaining ?? 2} 个会话 · ${meData?.anon_messages_remaining_per_session ?? 3} 轮/会话`
                    : user?.username}
                </div>
              </div>
              <Settings className="h-4 w-4 text-neutral-400" />
            </button>

            {/* 设置下拉菜单 */}
            {menuOpen && !isAnonymous && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
                <div className="absolute bottom-full left-0 right-0 z-50 mb-2 overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-lg dark:border-neutral-700 dark:bg-neutral-900">
                  <button
                    className="flex w-full items-center gap-2 px-3 py-2.5 text-sm text-neutral-700 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-800"
                    onClick={() => { setMenuOpen(false); openProfileModal(); }}
                  >
                    <UserIcon className="h-4 w-4" /> 个人中心
                  </button>
                  <button
                    className="flex w-full items-center gap-2 px-3 py-2.5 text-sm text-neutral-700 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-800"
                    onClick={() => { setMenuOpen(false); openSettingsModal(); }}
                  >
                    <Settings className="h-4 w-4" /> 设置
                  </button>
                  <div className="h-px bg-neutral-200 dark:bg-neutral-700" />
                  <button
                    className="flex w-full items-center gap-2 px-3 py-2.5 text-sm text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20 disabled:opacity-50"
                    onClick={handleLogout}
                    disabled={logoutLoading}
                  >
                    <LogOut className="h-4 w-4" /> {logoutLoading ? "退出中..." : "退出登录"}
                  </button>
                  {logoutError && (
                    <div className="px-3 py-1.5 text-xs text-red-600 dark:text-red-400">{logoutError}</div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </aside>

      {/* 删除会话确认 */}
      <Dialog open={Boolean(deleteId)} onOpenChange={(value) => !value && setDeleteId(null)}>
        <DialogContent>
          <DialogTitle className="text-lg font-semibold">删除这个分析会话？</DialogTitle>
          <DialogDescription className="mt-2 text-sm text-neutral-500">
            会话中的消息、文件和分析产物将一并删除，此操作无法撤销。
          </DialogDescription>
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDeleteId(null)}>取消</Button>
            <Button variant="destructive" onClick={() => { if (deleteId) onDelete(deleteId); setDeleteId(null); }}>
              确认删除
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* 登录 / 注册弹窗 */}
      <AuthModal
        open={authModalOpen}
        onOpenChange={(v) => (v ? openAuthModal() : closeAuthModal())}
        onSuccess={() => {
          void refetchMe();
          closeAuthModal();
        }}
      />

      {/* 个人中心弹窗 */}
      {user && (
        <ProfileModal
          open={profileModalOpen}
          onOpenChange={(v) => (v ? openProfileModal() : closeProfileModal())}
          user={user}
          onLogout={handleLogout}
          onAccountDeleted={handleLogout /* 删除后同样变成匿名态 */}
          onUpdated={() => void refetchMe()}
        />
      )}

      {/* 设置弹窗 */}
      <SettingsModal
        open={settingsModalOpen}
        onOpenChange={(v) => (v ? openSettingsModal() : closeSettingsModal())}
      />
    </>
  );
}
