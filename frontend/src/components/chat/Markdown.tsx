import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark, oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Check, Copy } from "lucide-react";
import { useChatStore } from "../../store/chatStore";

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const theme = useChatStore((state) => state.theme);
  const copy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };
  return <div className="relative my-3 overflow-hidden rounded-xl bg-neutral-950"><button className="absolute right-2 top-2 z-10 rounded-md bg-white/10 p-1.5 text-white hover:bg-white/20" onClick={() => void copy()} aria-label="复制代码">{copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}</button><SyntaxHighlighter language={language || "text"} style={theme === "dark" ? oneDark : oneLight} customStyle={{ margin: 0, padding: "1rem", maxHeight: "24rem", background: theme === "dark" ? "#0a0a0a" : "#f5f5f5", fontSize: "0.8rem" }}>{code}</SyntaxHighlighter></div>;
}

export function Markdown({ content }: { content: string }) {
  return <div className="markdown text-[15px] leading-7 text-neutral-800 dark:text-neutral-200"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{
    a: ({ children, ...props }) => <a {...props} target="_blank" rel="noreferrer" className="text-blue-600 underline">{children}</a>,
    pre: ({ children }) => <>{children}</>,
    code: ({ className, children }) => {
      const code = String(children).replace(/\n$/, "");
      const language = /language-(\w+)/.exec(className || "")?.[1] || "";
      if (!language && !code.includes("\n")) return <code className="rounded bg-neutral-100 px-1.5 py-0.5 text-[0.9em] dark:bg-neutral-800">{code}</code>;
      return <CodeBlock language={language} code={code} />;
    },
  }}>{content}</ReactMarkdown></div>;
}
