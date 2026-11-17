import { useEffect, useState } from "react";
import { RefreshCw, Loader2 } from "lucide-react";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogTitle } from "../ui/dialog";
import { api } from "../../api/endpoints";
import type { LoginRequest, RegisterRequest } from "../../types/api";

type Mode = "login" | "register";

interface AuthModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}

export function AuthModal({ open, onOpenChange, onSuccess }: AuthModalProps) {
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [captchaCode, setCaptchaCode] = useState("");
  const [captchaId, setCaptchaId] = useState("");
  const [captchaImage, setCaptchaImage] = useState("");
  const [captchaLoading, setCaptchaLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadCaptcha() {
    setCaptchaLoading(true);
    setError(null);
    try {
      const data = await api.captcha();
      setCaptchaId(data.captcha_id);
      setCaptchaImage(data.image);
      setCaptchaCode("");
    } catch {
      setError("验证码加载失败，请重试");
    } finally {
      setCaptchaLoading(false);
    }
  }

  useEffect(() => {
    if (open) loadCaptcha();
  }, [open, mode]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!username.trim() || !password.trim()) {
      setError("请填写用户名和密码");
      return;
    }
    if (!captchaCode.trim()) {
      setError("请输入验证码");
      return;
    }

    setSubmitting(true);
    try {
      if (mode === "login") {
        const payload: LoginRequest = {
          username: username.trim(),
          password,
          captcha_id: captchaId,
          captcha_code: captchaCode.trim(),
        };
        await api.login(payload);
      } else {
        const payload: RegisterRequest = {
          username: username.trim(),
          password,
          display_name: displayName.trim() || null,
          captcha_id: captchaId,
          captcha_code: captchaCode.trim(),
        };
        await api.register(payload);
      }
      onSuccess();
      onOpenChange(false);
    } catch (err: any) {
      const msg = err?.message || "操作失败，请稍后重试";
      setError(msg);
      loadCaptcha();
    } finally {
      setSubmitting(false);
    }
  }

  function reset() {
    setUsername("");
    setPassword("");
    setDisplayName("");
    setCaptchaCode("");
    setError(null);
  }

  useEffect(() => {
    reset();
  }, [mode]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md p-0">
        <div className="px-6 pt-6">
          <DialogTitle className="text-xl font-semibold">
            {mode === "login" ? "登录数据分析 Agent" : "注册新账号"}
          </DialogTitle>
          <p className="mt-1 text-sm text-neutral-500">
            {mode === "login"
              ? "登录后可创建更多会话和无限轮对话"
              : "注册后即可使用完整功能"}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 px-6 pb-6">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-neutral-700 dark:text-neutral-300">
              用户名
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="3-64 位字母/数字/下划线"
              className="h-10 w-full rounded-lg border border-neutral-200 bg-white px-3 text-sm outline-none transition-colors placeholder:text-neutral-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-neutral-700 dark:bg-neutral-900"
              autoComplete="username"
              disabled={submitting}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-neutral-700 dark:text-neutral-300">
              密码
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === "register" ? "至少 6 位" : ""}
              className="h-10 w-full rounded-lg border border-neutral-200 bg-white px-3 text-sm outline-none transition-colors placeholder:text-neutral-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-neutral-700 dark:bg-neutral-900"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              disabled={submitting}
            />
          </div>

          {mode === "register" && (
            <div>
              <label className="mb-1.5 block text-xs font-medium text-neutral-700 dark:text-neutral-300">
                昵称 <span className="text-neutral-400">（可选）</span>
              </label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="不填则使用用户名"
                className="h-10 w-full rounded-lg border border-neutral-200 bg-white px-3 text-sm outline-none transition-colors placeholder:text-neutral-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-neutral-700 dark:bg-neutral-900"
                disabled={submitting}
              />
            </div>
          )}

          <div>
            <label className="mb-1.5 block text-xs font-medium text-neutral-700 dark:text-neutral-300">
              验证码
            </label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={captchaCode}
                onChange={(e) => setCaptchaCode(e.target.value)}
                placeholder="4 位数字"
                maxLength={6}
                className="h-10 flex-1 rounded-lg border border-neutral-200 bg-white px-3 text-sm outline-none transition-colors placeholder:text-neutral-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-neutral-700 dark:bg-neutral-900"
                disabled={submitting}
              />
              <div className="flex h-10 items-center overflow-hidden rounded-lg border border-neutral-200 bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-800">
                {captchaLoading ? (
                  <div className="flex h-full w-[140px] items-center justify-center">
                    <Loader2 className="h-4 w-4 animate-spin text-neutral-400" />
                  </div>
                ) : (
                  <img src={captchaImage} alt="验证码" className="h-10 w-[140px] object-contain" />
                )}
                <button
                  type="button"
                  onClick={loadCaptcha}
                  disabled={captchaLoading || submitting}
                  className="flex h-full w-9 items-center justify-center border-l border-neutral-200 text-neutral-500 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-700"
                  aria-label="刷新验证码"
                >
                  <RefreshCw className={`h-4 w-4 ${captchaLoading ? "animate-spin" : ""}`} />
                </button>
              </div>
            </div>
          </div>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-400">
              {error}
            </div>
          )}

          <Button type="submit" disabled={submitting || captchaLoading} className="w-full">
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {mode === "login" ? "登录" : "注册"}
          </Button>

          <div className="text-center text-sm text-neutral-500">
            {mode === "login" ? "还没有账号？" : "已有账号？"}
            <button
              type="button"
              onClick={() => setMode(mode === "login" ? "register" : "login")}
              className="ml-1 font-medium text-blue-600 hover:underline dark:text-blue-400"
              disabled={submitting}
            >
              {mode === "login" ? "立即注册" : "去登录"}
            </button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
