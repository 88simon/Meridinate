'use client';

import { createContext, useContext } from 'react';

interface CodexContextType {
  isCodexOpen: boolean;
}

const CodexContext = createContext<CodexContextType>({ isCodexOpen: false });

export function useCodex() {
  return useContext(CodexContext);
}

export { CodexContext };
