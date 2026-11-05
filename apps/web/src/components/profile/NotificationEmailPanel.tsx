"use client";

import { useEffect, useState } from "react";
import { useLang } from "@/i18n";
import {
  emailError,
  getNotificationEmail,
  removeNotificationEmail,
  saveNotificationEmail,
  type EmailError,
  type NotificationEmail,
} from "@/lib/profiles/email";
import { Button } from "../ui/Button";
import { TextField } from "../ui/TextField";

const COPY = {
  en: {
    title: "Notification email", description: "Receive CampusPulse demo updates at an address you choose.",
    address: "Email address", consent: "This is my own email address and I agree to receive CampusPulse demo emails at it.",
    shared: "This is a shared demo account. The last saved address receives its updates.",
    disabled: "Email opt-in is currently off. You can still remove a saved address.",
    save: "Save", remove: "Remove", saved: "Notification email saved.", removed: "Notification email removed.",
    consentRequired: "Tick the consent box to save this address.", loading: "Loading notification email…",
    error: { session: "Please sign in again.", invalid: "Enter one valid email address and consent to receive demo mail.",
      limit: "Too many changes. Try again in an hour.", disabled: "Email opt-in is currently off.",
      waking: "The service is starting. Try again shortly.", generic: "Could not update the email. Try again." },
  },
  ar: {
    title: "البريد الإلكتروني للتنبيهات", description: "استقبل تحديثات كامبس بالس التجريبية على عنوان تختاره.",
    address: "عنوان البريد الإلكتروني", consent: "هذا عنوان بريدي الإلكتروني وأوافق على استلام رسائل كامبس بالس التجريبية عليه.",
    shared: "هذا حساب تجريبي مشترك. آخر عنوان محفوظ يستقبل التحديثات.",
    disabled: "الاشتراك بالبريد متوقف حالياً. يمكنك إزالة العنوان المحفوظ.",
    save: "حفظ", remove: "إزالة", saved: "تم حفظ بريد التنبيهات.", removed: "تمت إزالة بريد التنبيهات.",
    consentRequired: "يرجى الموافقة قبل حفظ العنوان.", loading: "جارٍ تحميل بريد التنبيهات…",
    error: { session: "يرجى تسجيل الدخول مجدداً.", invalid: "أدخل عنوان بريد واحداً صالحاً ووافق على استلام الرسائل التجريبية.",
      limit: "تم إجراء تغييرات كثيرة. حاول بعد ساعة.", disabled: "الاشتراك بالبريد متوقف حالياً.",
      waking: "الخدمة قيد التشغيل. حاول بعد قليل.", generic: "تعذر تحديث البريد. حاول مجدداً." },
  },
} as const;

type Notice = { kind: "ok"; text: string } | { kind: "error"; error: EmailError } | null;

export function NotificationEmailPanel() {
  const { lang } = useLang();
  const copy = COPY[lang];
  const [current, setCurrent] = useState<NotificationEmail | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [address, setAddress] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  useEffect(() => {
    let active = true;
    void getNotificationEmail().then((result) => {
      if (!active) return;
      if (result.ok) { setCurrent(result.data); setAddress(result.data.email ?? ""); }
      else setNotice({ kind: "error", error: emailError(result) });
      setLoaded(true);
    });
    return () => { active = false; };
  }, []);

  const save = async () => {
    if (!consent) { setNotice({ kind: "error", error: "invalid" }); return; }
    setBusy(true); setNotice(null);
    const result = await saveNotificationEmail(address, true);
    setBusy(false);
    if (!result.ok) { setNotice({ kind: "error", error: emailError(result) }); return; }
    setCurrent(result.data); setAddress(result.data.email ?? ""); setConsent(false);
    setNotice({ kind: "ok", text: copy.saved });
  };

  const remove = async () => {
    setBusy(true); setNotice(null);
    const result = await removeNotificationEmail();
    setBusy(false);
    if (!result.ok) { setNotice({ kind: "error", error: emailError(result) }); return; }
    setCurrent(result.data); setAddress(""); setConsent(false);
    setNotice({ kind: "ok", text: copy.removed });
  };

  return (
    <section aria-label={copy.title} className="rounded-lg border border-line bg-surface-1 p-4">
      <h2 className="text-lg font-semibold text-fg-1">{copy.title}</h2>
      <p className="mt-1 text-sm text-fg-2">{copy.description}</p>
      <p className="mt-2 text-sm text-fg-2">{copy.shared}</p>
      {!loaded ? <p role="status" className="mt-3">{copy.loading}</p> : current && (
        <div className="mt-4 flex max-w-xl flex-col gap-3">
          <TextField label={copy.address} type="email" autoComplete="email" dir="ltr" value={address}
            onChange={(e) => { setAddress(e.target.value); setConsent(false); setNotice(null); }} disabled={busy || !current.opt_in_enabled} />
          <label className="flex min-h-11 items-start gap-3 text-sm text-fg-1">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)}
              disabled={busy || !current.opt_in_enabled} className="mt-1 size-5" />
            <span>{copy.consent}</span>
          </label>
          {!current.opt_in_enabled && <p className="text-sm text-fg-2">{copy.disabled}</p>}
          <div className="flex flex-wrap gap-2">
            <Button onClick={save} loading={busy} disabled={!current.opt_in_enabled || !address.trim() || !consent}>{copy.save}</Button>
            {current.email && <Button variant="secondary" onClick={remove} loading={busy}>{copy.remove}</Button>}
          </div>
        </div>
      )}
      {notice && <p role="status" className={`mt-3 text-sm ${notice.kind === "error" ? "text-danger" : "text-fg-1"}`}>
        {notice.kind === "ok" ? notice.text : copy.error[notice.error]}
      </p>}
    </section>
  );
}
