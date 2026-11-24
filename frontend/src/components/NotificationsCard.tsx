import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError, type NotificationKind, type NotificationSettings } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/**
 * The signed-in account's own e-mail notifications (backend
 * services/mail_notifications.py). Not rendered at all on an instance
 * without an SMTP server: a checkbox that can never send anything would be
 * a setting that lies.
 */
export function NotificationsCard() {
  const { t } = useI18n();
  const [state, setState] = useState<NotificationSettings | null>(null);
  const [email, setEmail] = useState("");
  const [chosen, setChosen] = useState<NotificationKind[]>([]);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    api
      .notifications()
      .then((s) => {
        setState(s);
        setEmail(s.email);
        setChosen(s.notify);
      })
      .catch(() => setState(null));
  }, []);

  if (!state?.enabled) return null;

  function toggle(kind: NotificationKind, on: boolean) {
    setChosen((current) => (on ? [...current, kind] : current.filter((k) => k !== kind)));
  }

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const saved = await api.setNotifications(email.trim(), chosen);
      setState({ ...state!, ...saved });
      toast.success(t("notify.saved"));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setSaving(false);
    }
  }

  async function onTest() {
    setTesting(true);
    try {
      await api.testNotification();
      toast.success(t("notify.testSent").replace("{email}", state!.email));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setTesting(false);
    }
  }

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="text-base font-semibold text-[var(--ink)]">{t("notify.title")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSave} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            {t("notify.email")}
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="max-w-sm" />
          </label>
          <fieldset className="flex flex-col gap-1.5 text-sm">
            <legend className="mb-1 font-medium">{t("notify.when")}</legend>
            {state.kinds.map((kind) => (
              <label key={kind} className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={chosen.includes(kind)}
                  onChange={(e) => toggle(kind, e.target.checked)}
                />
                <span>{t(`notify.kind.${kind}` as never)}</span>
              </label>
            ))}
          </fieldset>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={saving}>
              {t("notify.save")}
            </Button>
            {state.email && (
              <Button type="button" variant="outline" disabled={testing} onClick={() => void onTest()}>
                {t("notify.test")}
              </Button>
            )}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
