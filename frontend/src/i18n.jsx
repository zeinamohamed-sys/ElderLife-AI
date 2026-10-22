import { createContext, useContext, useEffect, useMemo, useState } from "react";
import en from "./locales/en.js";
import ar from "./locales/ar.js";

export const DICTS = { en, ar };
export const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "ar", label: "العربية" },
];
const STORAGE_KEY = "ui_lang";

if (import.meta.env.DEV) {
  const missing = Object.keys(en).filter((k) => !(k in ar));
  const extra = Object.keys(ar).filter((k) => !(k in en));
  const differ = Object.keys(en).filter((k) => k in ar && (en[k].match(/\{\w+\}/g) || []).sort().join() !== (ar[k].match(/\{\w+\}/g) || []).sort().join());
  if (missing.length || extra.length || differ.length) console.warn("i18n: en/ar mismatch", { missing, extra, differ });
}

/** Translate one key. Used by components through useI18n() and by api.js for its own messages. */
export function translate(lang, key, vars) {
  let text = (DICTS[lang] || en)[key] ?? en[key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) text = text.split("{" + k + "}").join(String(v));
  return text;
}

/** The language the user picked before, else the one their browser asks for. */
function detect() {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved && DICTS[saved]) return saved;
  return (navigator.language || "en").toLowerCase().startsWith("ar") ? "ar" : "en";
}

const Ctx = createContext(null);

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(detect);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";   // Arabic reads right to left
    localStorage.setItem(STORAGE_KEY, lang);
  }, [lang]);
  const value = useMemo(() => ({
    lang, setLang,
    t: (key, vars) => translate(lang, key, vars),
    fmt: (iso) => new Date(iso).toLocaleString(lang === "ar" ? "ar-EG-u-nu-latn" : [], { dateStyle: "short", timeStyle: "short" }),
  }), [lang]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useI18n = () => useContext(Ctx);

/** Small switcher used on the sign-in screen, the person's screen and in Settings. */
export function LanguagePicker({ className = "" }) {
  const { lang, setLang } = useI18n();
  return (
    <select className={("lang " + className).trim()} value={lang} aria-label="Language / اللغة"
      onChange={(e) => setLang(e.target.value)}>
      {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
    </select>
  );
}
