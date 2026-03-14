"""
app/services/i18n.py — AutoTax-HUB v5.2
Multi-language support (i18n).
Supports: de, en, tr, fr, es, it, ar, zh
"""

TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── Auth messages ──────────────────────────────────────
    "account_created": {
        "de": "Konto erfolgreich erstellt.",
        "en": "Account created successfully.",
        "tr": "Hesap başarıyla oluşturuldu.",
        "fr": "Compte créé avec succès.",
        "es": "Cuenta creada con éxito.",
        "it": "Account creato con successo.",
        "ar": "تم إنشاء الحساب بنجاح.",
        "zh": "账户创建成功。",
    },
    "account_created_verify": {
        "de": "Konto erstellt. Bitte bestätigen Sie Ihre E-Mail.",
        "en": "Account created. Please verify your email.",
        "tr": "Hesap oluşturuldu. Lütfen e-postanızı doğrulayın.",
        "fr": "Compte créé. Veuillez vérifier votre e-mail.",
        "es": "Cuenta creada. Por favor verifique su correo.",
        "it": "Account creato. Verifica la tua email.",
        "ar": "تم إنشاء الحساب. يرجى التحقق من بريدك الإلكتروني.",
        "zh": "账户已创建。请验证您的电子邮件。",
    },
    "invalid_credentials": {
        "de": "Ungültige E-Mail oder Passwort",
        "en": "Invalid email or password",
        "tr": "Geçersiz e-posta veya şifre",
        "fr": "E-mail ou mot de passe invalide",
        "es": "Correo o contraseña inválidos",
        "it": "Email o password non validi",
        "ar": "البريد الإلكتروني أو كلمة المرور غير صالحة",
        "zh": "无效的电子邮件或密码",
    },
    "account_locked": {
        "de": "Konto gesperrt. Versuchen Sie es in {minutes} Minuten erneut.",
        "en": "Account locked. Try again in {minutes} minutes.",
        "tr": "Hesap kilitlendi. {minutes} dakika sonra tekrar deneyin.",
        "fr": "Compte verrouillé. Réessayez dans {minutes} minutes.",
        "es": "Cuenta bloqueada. Intente en {minutes} minutos.",
        "it": "Account bloccato. Riprova tra {minutes} minuti.",
        "ar": "الحساب مقفل. حاول مرة أخرى بعد {minutes} دقيقة.",
        "zh": "账户已锁定。请在{minutes}分钟后重试。",
    },
    "account_disabled": {
        "de": "Konto deaktiviert",
        "en": "Account disabled",
        "tr": "Hesap devre dışı",
        "fr": "Compte désactivé",
        "es": "Cuenta desactivada",
        "it": "Account disabilitato",
        "ar": "الحساب معطل",
        "zh": "账户已禁用",
    },
    "email_not_verified": {
        "de": "E-Mail nicht bestätigt. Bitte prüfen Sie Ihren Posteingang.",
        "en": "Email not verified. Please check your inbox.",
        "tr": "E-posta doğrulanmadı. Lütfen gelen kutunuzu kontrol edin.",
        "fr": "E-mail non vérifié. Vérifiez votre boîte de réception.",
        "es": "Correo no verificado. Revise su bandeja de entrada.",
        "it": "Email non verificata. Controlla la tua casella di posta.",
        "ar": "لم يتم التحقق من البريد الإلكتروني. يرجى التحقق من صندوق الوارد.",
        "zh": "邮箱未验证。请检查您的收件箱。",
    },
    "email_already_registered": {
        "de": "E-Mail bereits registriert",
        "en": "Email already registered",
        "tr": "E-posta zaten kayıtlı",
        "fr": "E-mail déjà enregistré",
        "es": "Correo ya registrado",
        "it": "Email già registrata",
        "ar": "البريد الإلكتروني مسجل بالفعل",
        "zh": "邮箱已注册",
    },
    "logged_out": {
        "de": "Erfolgreich abgemeldet",
        "en": "Logged out successfully",
        "tr": "Başarıyla çıkış yapıldı",
        "fr": "Déconnexion réussie",
        "es": "Sesión cerrada con éxito",
        "it": "Disconnessione riuscita",
        "ar": "تم تسجيل الخروج بنجاح",
        "zh": "成功注销",
    },
    "email_verified": {
        "de": "E-Mail erfolgreich bestätigt",
        "en": "Email verified successfully",
        "tr": "E-posta başarıyla doğrulandı",
        "fr": "E-mail vérifié avec succès",
        "es": "Correo verificado con éxito",
        "it": "Email verificata con successo",
        "ar": "تم التحقق من البريد الإلكتروني بنجاح",
        "zh": "邮箱验证成功",
    },
    "password_reset_sent": {
        "de": "Wenn diese E-Mail registriert ist, wurde ein Link gesendet.",
        "en": "If that email is registered, a reset link has been sent.",
        "tr": "Bu e-posta kayıtlıysa, sıfırlama bağlantısı gönderildi.",
        "fr": "Si cet e-mail est enregistré, un lien a été envoyé.",
        "es": "Si ese correo está registrado, se ha enviado un enlace.",
        "it": "Se questa email è registrata, è stato inviato un link.",
        "ar": "إذا كان هذا البريد مسجلاً، فقد تم إرسال رابط إعادة التعيين.",
        "zh": "如果该邮箱已注册，重置链接已发送。",
    },
    "password_reset_success": {
        "de": "Passwort erfolgreich zurückgesetzt. Bitte erneut anmelden.",
        "en": "Password reset successfully. Please log in.",
        "tr": "Şifre başarıyla sıfırlandı. Lütfen giriş yapın.",
        "fr": "Mot de passe réinitialisé. Veuillez vous reconnecter.",
        "es": "Contraseña restablecida. Inicie sesión de nuevo.",
        "it": "Password reimpostata. Effettua nuovamente l'accesso.",
        "ar": "تمت إعادة تعيين كلمة المرور بنجاح. يرجى تسجيل الدخول.",
        "zh": "密码重置成功。请重新登录。",
    },

    # ── Invoice messages ───────────────────────────────────
    "invoice_not_found": {
        "de": "Rechnung nicht gefunden",
        "en": "Invoice not found",
        "tr": "Fatura bulunamadı",
        "fr": "Facture non trouvée",
        "es": "Factura no encontrada",
        "it": "Fattura non trovata",
        "ar": "الفاتورة غير موجودة",
        "zh": "未找到发票",
    },
    "duplicate_invoice": {
        "de": "Diese Rechnung wurde bereits hochgeladen (ID: {id})",
        "en": "This invoice has already been uploaded (ID: {id})",
        "tr": "Bu fatura zaten yüklendi (ID: {id})",
        "fr": "Cette facture a déjà été téléchargée (ID : {id})",
        "es": "Esta factura ya fue subida (ID: {id})",
        "it": "Questa fattura è già stata caricata (ID: {id})",
        "ar": "تم تحميل هذه الفاتورة بالفعل (ID: {id})",
        "zh": "此发票已上传 (ID: {id})",
    },
    "batch_max_exceeded": {
        "de": "Maximal 20 Dateien pro Batch-Upload erlaubt.",
        "en": "Maximum 20 files per batch upload allowed.",
        "tr": "Toplu yüklemede en fazla 20 dosya yüklenebilir.",
        "fr": "Maximum 20 fichiers par téléchargement groupé.",
        "es": "Máximo 20 archivos por carga masiva.",
        "it": "Massimo 20 file per caricamento batch.",
        "ar": "الحد الأقصى 20 ملفًا لكل تحميل دفعي.",
        "zh": "每次批量上传最多20个文件。",
    },
    "file_too_large": {
        "de": "Datei überschreitet das {mb}MB-Limit",
        "en": "File exceeds {mb}MB limit",
        "tr": "Dosya {mb}MB sınırını aşıyor",
        "fr": "Le fichier dépasse la limite de {mb}Mo",
        "es": "El archivo supera el límite de {mb}MB",
        "it": "Il file supera il limite di {mb}MB",
        "ar": "الملف يتجاوز حد {mb} ميجابايت",
        "zh": "文件超过{mb}MB限制",
    },
    "unsupported_file_type": {
        "de": "Nicht unterstützter Dateityp. Erlaubt: PDF, PNG, JPG, WEBP, TIFF",
        "en": "Unsupported file type. Allowed: PDF, PNG, JPG, WEBP, TIFF",
        "tr": "Desteklenmeyen dosya türü. İzin verilen: PDF, PNG, JPG, WEBP, TIFF",
        "fr": "Type de fichier non supporté. Autorisé : PDF, PNG, JPG, WEBP, TIFF",
        "es": "Tipo de archivo no soportado. Permitidos: PDF, PNG, JPG, WEBP, TIFF",
        "it": "Tipo di file non supportato. Consentiti: PDF, PNG, JPG, WEBP, TIFF",
        "ar": "نوع ملف غير مدعوم. المسموح: PDF, PNG, JPG, WEBP, TIFF",
        "zh": "不支持的文件类型。允许：PDF, PNG, JPG, WEBP, TIFF",
    },

    # ── Dashboard labels ───────────────────────────────────
    "income": {
        "de": "Einnahmen", "en": "Income", "tr": "Gelir",
        "fr": "Revenus", "es": "Ingresos", "it": "Entrate",
        "ar": "الدخل", "zh": "收入",
    },
    "expenses": {
        "de": "Ausgaben", "en": "Expenses", "tr": "Giderler",
        "fr": "Dépenses", "es": "Gastos", "it": "Spese",
        "ar": "المصروفات", "zh": "支出",
    },
    "net_profit": {
        "de": "Nettogewinn", "en": "Net Profit", "tr": "Net Kâr",
        "fr": "Bénéfice net", "es": "Beneficio neto", "it": "Utile netto",
        "ar": "صافي الربح", "zh": "净利润",
    },
    "tax_estimate": {
        "de": "Geschätzte Steuer", "en": "Tax Estimate", "tr": "Tahmini Vergi",
        "fr": "Estimation d'impôt", "es": "Estimación de impuestos", "it": "Stima fiscale",
        "ar": "تقدير الضريبة", "zh": "税费估算",
    },

    # ── General ────────────────────────────────────────────
    "internal_error": {
        "de": "Interner Serverfehler",
        "en": "Internal server error",
        "tr": "Sunucu hatası",
        "fr": "Erreur interne du serveur",
        "es": "Error interno del servidor",
        "it": "Errore interno del server",
        "ar": "خطأ داخلي في الخادم",
        "zh": "内部服务器错误",
    },
}

# Default language
_DEFAULT_LANG = "de"


def t(key: str, lang: str = "de", **kwargs) -> str:
    """
    Translate a message key to the specified language.
    Falls back to German, then English, then returns the key itself.
    Supports {placeholder} substitution via kwargs.
    """
    lang = lang.lower()[:2] if lang else _DEFAULT_LANG

    messages = TRANSLATIONS.get(key)
    if not messages:
        return key

    text = messages.get(lang) or messages.get(_DEFAULT_LANG) or messages.get("en", key)

    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass

    return text


def get_supported_languages() -> list[dict]:
    """List all supported languages."""
    lang_names = {
        "de": "Deutsch",
        "en": "English",
        "tr": "Türkçe",
        "fr": "Français",
        "es": "Español",
        "it": "Italiano",
        "ar": "العربية",
        "zh": "中文",
    }
    return [{"code": code, "name": name} for code, name in lang_names.items()]
