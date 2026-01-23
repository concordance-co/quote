import { useState, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { Key, Loader2, AlertCircle, LogOut, User } from "lucide-react";

interface LoginModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function LoginModal({ open, onOpenChange }: LoginModalProps) {
  const { login, isLoading, error, clearError } = useAuth();
  const [apiKey, setApiKey] = useState("");

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!apiKey.trim()) return;

      const success = await login(apiKey.trim());
      if (success) {
        setApiKey("");
        onOpenChange(false);
      }
    },
    [apiKey, login, onOpenChange],
  );

  const handleOpenChange = useCallback(
    (newOpen: boolean) => {
      if (!newOpen) {
        clearError();
        setApiKey("");
      }
      onOpenChange(newOpen);
    },
    [clearError, onOpenChange],
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Key className="h-5 w-5" />
            Sign In
          </DialogTitle>
          <DialogDescription>
            Enter your API key to access your data. Your key will be stored
            locally in your browser.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <div className="space-y-4 py-4">
            {error && (
              <div className="flex items-center gap-2 p-3 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/50 rounded-md border border-red-200 dark:border-red-800">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}
            <div className="space-y-2">
              <label
                htmlFor="apiKey"
                className="text-sm font-medium text-foreground"
              >
                API Key
              </label>
              <input
                id="apiKey"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Enter your API key..."
                className="w-full px-3 py-2 text-sm border border-input rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent disabled:opacity-50"
                disabled={isLoading}
                autoFocus
              />
              <p className="text-xs text-muted-foreground">
                Use the same API key you use for inference requests, or an admin
                key provided by your administrator.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isLoading}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isLoading || !apiKey.trim()}>
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Validating...
                </>
              ) : (
                "Sign In"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

interface UserMenuProps {
  onLogout: () => void;
  userName: string;
  isAdmin: boolean;
}

export function UserMenu({ onLogout, userName, isAdmin }: UserMenuProps) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted text-xs">
        <User className="h-3 w-3" />
        <span className="font-medium">{userName}</span>
        {isAdmin && (
          <span className="px-1 py-0.5 rounded text-2xs bg-primary/10 text-primary">
            Admin
          </span>
        )}
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="h-7 text-xs px-2"
        onClick={onLogout}
      >
        <LogOut className="h-3 w-3 mr-1" />
        Sign Out
      </Button>
    </div>
  );
}

export default LoginModal;
