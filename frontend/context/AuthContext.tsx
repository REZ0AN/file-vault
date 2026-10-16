
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type { ReactNode } from "react";

import { api } from "@/lib/api";
import type { User } from "@/lib/api";


// --------------------------------------------------
// Types
// --------------------------------------------------

type AuthSession = {
  user: User;
  accessToken: string;
  expiresAt: number;
};

type LoginCredentials = {
  email: string;
  password: string;
};

type AuthContextValue = {
  user: User | null;
  accessToken: string | null;
  expiresAt: number | null;
  isAuthenticated: boolean;
  isLoading: boolean;

  login: (
    credentials: LoginCredentials
  ) => Promise<User>;

  logout: () => void;

  getAccessToken: () => string | null;
};


// --------------------------------------------------
// Context
// --------------------------------------------------

const AuthContext = createContext<
  AuthContextValue | undefined
>(undefined);


// Expire slightly before the JWT's actual expiry.
// This reduces requests sent near the deadline.
const EXPIRY_SAFETY_MARGIN_MS = 5000;


// --------------------------------------------------
// Provider
// --------------------------------------------------

export function AuthProvider({
  children,
}: {
  children: ReactNode;
}) {
  // React memory only: no browser storage.
  const [session, setSession] =
    useState<AuthSession | null>(null);

  const [isLoading, setIsLoading] = useState(false);

  // Tracks authentication operations so that an
  // older login cannot overwrite a later logout.
  const authVersion = useRef(0);

  // Avoid simultaneous login submissions.
  const loginInProgress = useRef(false);


  // -----------------------------------------------
  // Logout
  // -----------------------------------------------

  const logout = useCallback(() => {
    authVersion.current += 1;

    setSession(null);
    setIsLoading(false);
  }, []);


  // -----------------------------------------------
  // Login
  // -----------------------------------------------

  const login = useCallback(
    async (
      credentials: LoginCredentials
    ): Promise<User> => {
      if (loginInProgress.current) {
        throw new Error(
          "A login request is already in progress."
        );
      }

      loginInProgress.current = true;

      const operationVersion =
        ++authVersion.current;

      setIsLoading(true);

      try {
        // 1. Authenticate with FastAPI.
        const result = await api.login({
          email: credentials.email.trim().toLowerCase(),
          password: credentials.password,
        });

        // 2. Calculate expiration from the
        // response's expires_in value.
        const expiresAt =
          Date.now() +
          result.expires_in * 1000 -
          EXPIRY_SAFETY_MARGIN_MS;

        if (
          !Number.isFinite(expiresAt) ||
          expiresAt <= Date.now()
        ) {
          throw new Error(
            "Received an expired access token."
          );
        }

        // 3. Validate the token by retrieving
        // the authenticated user.
        const user = await api.getMe(
          result.access_token
        );

        // 4. A logout may have happened while
        // the requests were in progress.
        if (
          operationVersion !== authVersion.current
        ) {
          throw new Error(
            "Login was cancelled."
          );
        }

        if (Date.now() >= expiresAt) {
          throw new Error(
            "Access token expired during login."
          );
        }

        // 5. Store only in React memory.
        setSession({
          user,
          accessToken: result.access_token,
          expiresAt,
        });

        return user;
      } finally {
        loginInProgress.current = false;

        if (
          operationVersion === authVersion.current
        ) {
          setIsLoading(false);
        }
      }
    },
    []
  );


  // -----------------------------------------------
  // Expire the session automatically
  // -----------------------------------------------

  useEffect(() => {
    if (!session) {
      return;
    }

    const remainingMs =
      session.expiresAt - Date.now();

    if (remainingMs <= 0) {
      const timeout = window.setTimeout(
        logout,
        0
      );

      return () => window.clearTimeout(timeout);
    }

    const timeout = window.setTimeout(
      logout,
      remainingMs
    );

    return () => {
      window.clearTimeout(timeout);
    };
  }, [session, logout]);


  // -----------------------------------------------
  // Safely retrieve a non-expired token
  // -----------------------------------------------

  const getAccessToken = useCallback(() => {
    if (!session) {
      return null;
    }

    if (Date.now() >= session.expiresAt) {
      return null;
    }

    return session.accessToken;
  }, [session]);


  // -----------------------------------------------
  // Shared context value
  // -----------------------------------------------

  const value = useMemo<AuthContextValue>(() => {
    const validSession =
      session !== null &&
      Date.now() < session.expiresAt;

    return {
      user: validSession ? session.user : null,

      accessToken: validSession
        ? session.accessToken
        : null,

      expiresAt: validSession
        ? session.expiresAt
        : null,

      isAuthenticated: validSession,

      isLoading,

      login,
      logout,
      getAccessToken,
    };
  }, [
    session,
    isLoading,
    login,
    logout,
    getAccessToken,
  ]);


  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}


// --------------------------------------------------
// Reusable authentication hook
// --------------------------------------------------

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);

  if (context === undefined) {
    throw new Error(
      "useAuth must be used inside AuthProvider."
    );
  }

  return context;
}
