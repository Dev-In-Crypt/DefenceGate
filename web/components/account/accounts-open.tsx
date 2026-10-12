'use client';

import { createContext, useContext } from 'react';

/**
 * Whether accounts are open, as the public layout read it from /v1/account/status (cached 60 seconds).
 * When they are not, the save and follow islands show "Sign in to save" without asking the server anything.
 */
const AccountsOpenContext = createContext(false);

export function AccountsOpenProvider({ open, children }: { open: boolean; children: React.ReactNode }) {
  return <AccountsOpenContext.Provider value={open}>{children}</AccountsOpenContext.Provider>;
}

export const useAccountsOpen = () => useContext(AccountsOpenContext);
