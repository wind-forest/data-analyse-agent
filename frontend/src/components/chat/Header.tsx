import * as Select from "@radix-ui/react-select";
import { BarChart3, Check, ChevronDown, FileText, Menu, Moon, Sun } from "lucide-react";
import type { AppConfig, Session } from "../../types/api";
import { useChatStore } from "../../store/chatStore";
import { Button } from "../ui/button";

interface HeaderProps {
  session?: Session;
  config?: AppConfig;
  fileCount: number;
  artifactCount: number;
}

export function Header({ session, config, fileCount, artifactCount }: HeaderProps) {
  const model = useChatStore((state) => state.model);
  const setModel = useChatStore((state) => state.setModel);
  const theme = useChatStore((state) => state.theme);
  const toggleTheme = useChatStore((state) => state.toggleTheme);
  const setSidebarOpen = useChatStore((state) => state.setSidebarOpen);
  const setArtifactsOpen = useChatStore((state) => state.setArtifactsOpen);

  return (
    <header className="flex h-16 shrink-0 items-center gap-2 border-b border-neutral-200 bg-white/90 px-3 dark:border-neutral-800 dark:bg-neutral-900/90 md:px-5">
      <Button variant="ghost" size="icon" className="md:hidden" aria-label="打开会话列表" onClick={() => setSidebarOpen(true)}><Menu className="h-5 w-5" /></Button>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-sm font-semibold md:text-base">{session?.title || "数据分析 Agent"}</h1>
        {session && <div className="mt-0.5 flex items-center gap-1 text-xs text-neutral-500"><FileText className="h-3 w-3" />{fileCount} 个数据文件</div>}
      </div>
      {config && (
        <Select.Root value={model || config.default_model} onValueChange={setModel}>
          <Select.Trigger aria-label="选择模型" className="hidden h-9 items-center gap-2 rounded-lg border border-neutral-200 px-3 text-sm outline-none hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-800 sm:flex">
            <Select.Value /><Select.Icon><ChevronDown className="h-4 w-4" /></Select.Icon>
          </Select.Trigger>
          <Select.Portal><Select.Content position="popper" sideOffset={5} className="z-50 min-w-44 rounded-lg border border-neutral-200 bg-white p-1 shadow-xl dark:border-neutral-700 dark:bg-neutral-900">
            <Select.Viewport>{config.allowed_models.map((item) => <Select.Item key={item} value={item} className="flex cursor-pointer items-center justify-between rounded-md px-3 py-2 text-sm outline-none focus:bg-neutral-100 dark:focus:bg-neutral-800"><Select.ItemText>{item}</Select.ItemText><Select.ItemIndicator><Check className="h-4 w-4" /></Select.ItemIndicator></Select.Item>)}</Select.Viewport>
          </Select.Content></Select.Portal>
        </Select.Root>
      )}
      <Button variant="ghost" size="icon" aria-label={theme === "light" ? "切换深色模式" : "切换浅色模式"} onClick={toggleTheme}>{theme === "light" ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}</Button>
      <Button variant="outline" size="sm" aria-label={`查看 ${artifactCount} 个分析产物`} onClick={() => setArtifactsOpen(true)}><BarChart3 className="h-4 w-4" /><span className="hidden sm:inline">产物</span>{artifactCount > 0 && <span className="rounded-full bg-neutral-100 px-1.5 dark:bg-neutral-800">{artifactCount}</span>}</Button>
    </header>
  );
}
