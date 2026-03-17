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
import {
  FormField,
  formFieldInputClassName,
} from "@/components/design-system/FormField";
import { cn } from "@/lib/utils";
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
      <DialogContent className="sm:max-w-md border-white/20 bg-[rgba(16,20,28,0.92)] backdrop-blur-xl">
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
              <div className="flex items-center gap-2 p-3 text-sm text-red-200 bg-red-900/35 rounded-md border border-red-700/60">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}
            <FormField
              label="API Key"
              helperText="Use the same API key you use for inference requests, or an admin key provided by your administrator."
            >
              <input
                id="apiKey"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Enter your API key..."
                className={formFieldInputClassName}
                disabled={isLoading}
                autoFocus
              />
            </FormField>
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
  tone?: "paper" | "ink";
}

export function UserMenu({
  onLogout,
  userName,
  isAdmin,
  tone = "paper",
}: UserMenuProps) {
  const isInk = tone === "ink";
  return (
    <div
      className={cn(
        "flex items-center gap-2",
        isInk ? "text-white" : "text-[var(--brand-ink)]",
      )}
    >
      <div className="flex items-center gap-1.5 font-mono text-xs uppercase tracking-[0.08em]">
        <User className="h-3 w-3" />
        <span className="font-medium normal-case tracking-normal">{userName}</span>
        {isAdmin && <span className="text-[10px] opacity-70 uppercase">Admin</span>}
      </div>
      <Button
        variant="ghost"
        size="sm"
        className={cn(
          "h-7 px-0 font-mono text-xs uppercase tracking-[0.08em]",
          isInk
            ? "text-white/85 hover:text-white"
            : "text-[var(--brand-ink)] hover:text-[var(--brand-ink)] hover:bg-black/10",
        )}
        onClick={onLogout}
      >
        <LogOut className="h-3 w-3 mr-1" />
        Sign Out
      </Button>
    </div>
  );
}

export default LoginModal;
