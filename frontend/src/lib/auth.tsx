import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
} from "react";
import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_URL || "/api";

// Storage key for persisting the API key
const API_KEY_STORAGE_KEY = "concordance_api_key";

// Types
export interface AuthUser {
  name: string;
  allowedApiKey: string | null;
  isAdmin: boolean;
}

export interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: AuthUser | null;
  apiKey: string | null;
  error: string | null;
}

export interface AuthContextType extends AuthState {
  login: (apiKey: string) => Promise<boolean>;
  logout: () => void;
  clearError: () => void;
}

// Default context value
const defaultAuthContext: AuthContextType = {
  isAuthenticated: false,
  isLoading: true,
  user: null,
  apiKey: null,
  error: null,
  login: async () => false,
  logout: () => {},
  clearError: () => {},
};

// Create the context
const AuthContext = createContext<AuthContextType>(defaultAuthContext);

// API response type
interface ValidateKeyResponse {
  valid: boolean;
  name: string | null;
  allowed_api_key: string | null;
  is_admin: boolean;
  message: string;
}

type ValidateApiKeyResult = {
  user: AuthUser | null;
  error: string | null;
};

// Provider component
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: false,
    isLoading: true,
    user: null,
    apiKey: null,
    error: null,
  });

  // Validate an API key against the backend
  const validateApiKey = useCallback(
    async (apiKey: string): Promise<ValidateApiKeyResult> => {
      try {
        const response = await axios.get<ValidateKeyResponse>(
          `${API_BASE_URL}/auth/validate`,
          {
            headers: {
              "X-API-Key": apiKey,
            },
          }
        );

        if (response.data.valid && response.data.name) {
          return {
            user: {
              name: response.data.name,
              allowedApiKey: response.data.allowed_api_key,
              isAdmin: response.data.is_admin,
            },
            error: null,
          };
        }
        return {
          user: null,
          error: "Invalid API key. Please check your key and try again.",
        };
      } catch (error) {
        if (axios.isAxiosError(error)) {
          if (!error.response) {
            return {
              user: null,
              error:
                "Cannot reach the API service. Confirm backend is running on localhost:8080.",
            };
          }

          if (error.response.status >= 500) {
            return {
              user: null,
              error:
                "Authentication service returned a server error. Check backend logs/config.",
            };
          }
        }

        return {
          user: null,
          error: "Invalid API key. Please check your key and try again.",
        };
      }
    },
    []
  );

  // Initialize auth state from localStorage
  useEffect(() => {
    const initAuth = async () => {
      const storedKey = localStorage.getItem(API_KEY_STORAGE_KEY);

      if (storedKey) {
        const result = await validateApiKey(storedKey);
        const user = result.user;
        if (user) {
          setState({
            isAuthenticated: true,
            isLoading: false,
            user,
            apiKey: storedKey,
            error: null,
          });
          return;
        } else {
          // Invalid stored key, remove it
          localStorage.removeItem(API_KEY_STORAGE_KEY);
        }
      }

      setState({
        isAuthenticated: false,
        isLoading: false,
        user: null,
        apiKey: null,
        error: null,
      });
    };

    initAuth();
  }, [validateApiKey]);

  // Login function
  const login = useCallback(
    async (apiKey: string): Promise<boolean> => {
      setState((prev) => ({ ...prev, isLoading: true, error: null }));

      const result = await validateApiKey(apiKey);
      const user = result.user;

      if (user) {
        localStorage.setItem(API_KEY_STORAGE_KEY, apiKey);
        setState({
          isAuthenticated: true,
          isLoading: false,
          user,
          apiKey,
          error: null,
        });
        return true;
      } else {
        setState((prev) => ({
          ...prev,
          isLoading: false,
          error:
            result.error ||
            "Invalid API key. Please check your key and try again.",
        }));
        return false;
      }
    },
    [validateApiKey]
  );

  // Logout function
  const logout = useCallback(() => {
    localStorage.removeItem(API_KEY_STORAGE_KEY);
    setState({
      isAuthenticated: false,
      isLoading: false,
      user: null,
      apiKey: null,
      error: null,
    });
  }, []);

  // Clear error
  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  // Memoize context value
  const contextValue = useMemo(
    () => ({
      ...state,
      login,
      logout,
      clearError,
    }),
    [state, login, logout, clearError]
  );

  return (
    <AuthContext.Provider value={contextValue}>{children}</AuthContext.Provider>
  );
}

// Hook for using auth context
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

// Helper to get stored API key (for axios interceptors)
export function getStoredApiKey(): string | null {
  return localStorage.getItem(API_KEY_STORAGE_KEY);
}

// Create an axios instance with auth headers
export function createAuthenticatedApi() {
  const instance = axios.create({
    baseURL: API_BASE_URL,
    headers: {
      "Content-Type": "application/json",
    },
  });

  // Add request interceptor to include API key
  instance.interceptors.request.use((config) => {
    const apiKey = getStoredApiKey();
    if (apiKey) {
      config.headers["X-API-Key"] = apiKey;
    }
    return config;
  });

  return instance;
}

export default AuthContext;
