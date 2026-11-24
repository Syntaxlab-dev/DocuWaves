// The signed-in user's own account: change the password.
// Split out of pages/AdminApp.tsx, which keeps the layout and state.
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export function AccountCard({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      toast.success(t("admin.passwordChanged"));
      setCurrentPassword("");
      setNewPassword("");
      onClose();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="text-base font-semibold text-[var(--ink)]">{t("admin.account")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex flex-1 flex-col gap-1.5">
            <label className="text-sm font-medium">{t("admin.currentPassword")}</label>
            <Input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} required />
          </div>
          <div className="flex flex-1 flex-col gap-1.5">
            <label className="text-sm font-medium">{t("admin.newPassword")}</label>
            <Input type="password" minLength={8} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required />
          </div>
          <Button type="submit" disabled={submitting}>
            {t("admin.changePassword")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
