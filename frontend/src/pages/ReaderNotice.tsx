import { BookOpen, LogOut } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

/** What a Reader account sees at /admin: what the account is for, the way to
 *  the docs, and signing out -- not an admin UI full of 403s. */
export function ReaderNotice({ username }: { username: string }) {
  const { t } = useI18n();
  const { refresh } = useAuth();

  async function signOut() {
    try {
      await api.logout();
    } finally {
      await refresh();
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--bg)] px-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-lg font-semibold text-[var(--ink)]">{t("reader.title")}</CardTitle>
          <p className="text-sm text-[var(--muted)]">{t("auth.signedInAs").replace("{name}", username)}</p>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="text-sm">{t("reader.body")}</p>
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm">
              <Link to="/">
                <BookOpen className="h-4 w-4" />
                {t("reader.toDocs")}
              </Link>
            </Button>
            <Button size="sm" variant="outline" onClick={signOut}>
              <LogOut className="h-4 w-4" />
              {t("auth.signOut")}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
