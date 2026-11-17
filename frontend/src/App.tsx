import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChatPage } from "./components/chat/ChatPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
});

export default function App() {
  return <QueryClientProvider client={queryClient}><ChatPage /></QueryClientProvider>;
}
