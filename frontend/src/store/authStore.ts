import { create } from "zustand";
import type { User } from "../types/api";

interface AuthState {
  user: User | null;
  anonSessionsRemaining: number;
  anonMessagesRemainingPerSession: number;
  initialized: boolean;
  authModalOpen: boolean;
  profileModalOpen: boolean;
  settingsModalOpen: boolean;
  setMe: (user: User | null, anonSessionsRemaining?: number, anonMessagesRemainingPerSession?: number) => void;
  setInitialized: (initialized: boolean) => void;
  logout: () => void;
  openAuthModal: () => void;
  closeAuthModal: () => void;
  openProfileModal: () => void;
  closeProfileModal: () => void;
  openSettingsModal: () => void;
  closeSettingsModal: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  anonSessionsRemaining: 2,
  anonMessagesRemainingPerSession: 3,
  initialized: false,
  authModalOpen: false,
  profileModalOpen: false,
  settingsModalOpen: false,
  setMe: (user, anonSessionsRemaining, anonMessagesRemainingPerSession) =>
    set({
      user,
      anonSessionsRemaining: anonSessionsRemaining ?? 2,
      anonMessagesRemainingPerSession: anonMessagesRemainingPerSession ?? 3,
      initialized: true,
    }),
  setInitialized: (initialized) => set({ initialized }),
  logout: () =>
    set({
      user: null,
      initialized: true,
      profileModalOpen: false,
      settingsModalOpen: false,
    }),
  openAuthModal: () => set({ authModalOpen: true }),
  closeAuthModal: () => set({ authModalOpen: false }),
  openProfileModal: () => set({ profileModalOpen: true }),
  closeProfileModal: () => set({ profileModalOpen: false }),
  openSettingsModal: () => set({ settingsModalOpen: true }),
  closeSettingsModal: () => set({ settingsModalOpen: false }),
}));
