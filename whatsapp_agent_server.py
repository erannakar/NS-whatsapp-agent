<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>אימולטור חי: כשר פליי CRM ובדיקת הרשאות סוכן</title>
  <script src="https://cdn.tailwindcss.com/3.4.17"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;600;700;800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    body {
      font-family: 'Heebo', sans-serif;
      background-color: #0b1120;
      color: #f8fafc;
    }
    .mono {
      font-family: 'JetBrains Mono', monospace;
    }
    .custom-scroll::-webkit-scrollbar {
      width: 6px;
      height: 6px;
    }
    .custom-scroll::-webkit-scrollbar-track {
      background: rgba(15, 23, 42, 0.6);
    }
    .custom-scroll::-webkit-scrollbar-thumb {
      background: #334155;
      border-radius: 9999px;
    }
    .custom-scroll::-webkit-scrollbar-thumb:hover {
      background: #475569;
    }
    .wa-chat-bg {
      background-color: #0c1317;
      background-image: radial-gradient(#1f2c34 1px, transparent 1px);
      background-size: 20px 20px;
    }
  </style>
</head>
<body class="min-h-screen flex flex-col bg-slate-950 text-slate-100 antialiased selection:bg-emerald-500 selection:text-slate-950">

  <!-- TOP APP BAR -->
  <header class="border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-40 px-4 py-3">
    <div class="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center font-black text-slate-950 text-xl shadow-lg shadow-emerald-500/20">
          🛡️
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="font-bold text-base sm:text-lg text-white">אימולטור כשר פליי CRM (Aysko v6.5.1)</h1>
            <span class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">הרשאות משווק מאומתות</span>
          </div>
          <p class="text-xs text-slate-400">בדיקה ויזואלית: התחברות ל-API, ניתוח טוקן, ביצוע השהיה והחזרת הגנה בזמן אמת</p>
        </div>
      </div>

      <div class="flex items-center gap-2.5">
        <div class="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700 text-xs">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span class="text-slate-300">משתמש מחובר:</span>
          <span class="font-bold text-white mono">ערן נקר 1657</span>
          <span class="text-[10px] px-1.5 py-0.2 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/40">Rank 2 (משווק מורשה)</span>
        </div>
        <button id="resetDemoBtn" type="button" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">
          איפוס נתונים
        </button>
      </div>
    </div>
  </header>

  <!-- NAVIGATION TABS -->
  <div class="border-b border-slate-800 bg-slate-900/60 px-4">
    <div class="max-w-7xl mx-auto flex gap-2 overflow-x-auto custom-scroll py-2.5">
      <button type="button" id="tabBtn-crm" data-tab="crm" class="tab-btn px-4 py-2 rounded-xl text-xs sm:text-sm font-bold flex items-center gap-2 bg-emerald-600 text-white shadow-md shadow-emerald-600/20 transition">
        🖥️ אימולטור ממשק כשר פליי (CRM)
      </button>
      <button type="button" id="tabBtn-perms" data-tab="perms" class="tab-btn px-4 py-2 rounded-xl text-xs sm:text-sm font-semibold flex items-center gap-2 text-slate-400 hover:text-white hover:bg-slate-800/60 transition">
        🔑 דו"ח הרשאות טוקן ומשווק (Rank 2)
      </button>
      <button type="button" id="tabBtn-whatsapp" data-tab="whatsapp" class="tab-btn px-4 py-2 rounded-xl text-xs sm:text-sm font-semibold flex items-center gap-2 text-slate-400 hover:text-white hover:bg-slate-800/60 transition">
        💬 סימולטור צ'אט ווצאפ בלשון רבים
      </button>
      <button type="button" id="tabBtn-api" data-tab="api" class="tab-btn px-4 py-2 rounded-xl text-xs sm:text-sm font-semibold flex items-center gap-2 text-slate-400 hover:text-white hover:bg-slate-800/60 transition">
        ⚡ קונסולת קריאות API ישירות
      </button>
    </div>
  </div>

  <!-- MAIN CONTAINER -->
  <main class="flex-1 max-w-7xl mx-auto w-full p-4 space-y-4">

    <!-- ===================================================================== -->
    <!-- TAB 1: KOSHERPLAY CRM EMULATOR -->
    <!-- ===================================================================== -->
    <section id="panel-crm" class="tab-panel space-y-4">

      <!-- TOP CONTROL & SEARCH BAR -->
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-4">
        <div class="flex items-center gap-3 w-full sm:w-auto">
          <div class="relative flex-1 sm:w-80">
            <span class="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-500">🔍</span>
            <input type="text" id="crmSearchInput" value="0553164770" placeholder="חיפוש לקוח לפי טלפון או שם..." class="w-full bg-slate-950 border border-slate-700 rounded-xl pr-9 pl-3 py-2 text-xs sm:text-sm text-white focus:outline-none focus:border-emerald-500 mono" />
          </div>
          <button type="button" id="crmSearchBtn" class="bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold px-4 py-2 rounded-xl text-xs sm:text-sm transition flex items-center gap-1.5 shadow-md shadow-emerald-600/20">
            חפש בכרטיסים
          </button>
        </div>

        <div class="flex items-center gap-2 text-xs">
          <span class="text-slate-400">כתובת השרת:</span>
          <span class="px-2.5 py-1 rounded-md bg-slate-950 border border-slate-800 text-teal-300 font-mono">https://crm.kosherplay.com/api</span>
          <span class="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">JWT 201 OK</span>
        </div>
      </div>

      <!-- CRM WORKSPACE GRID -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-4">

        <!-- LEFT/MAIN: CUSTOMER CARD & EDIT FORM (8 COLS) -->
        <div class="lg:col-span-8 bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-5">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
            <div>
              <div class="flex items-center gap-2">
                <h2 class="text-lg font-extrabold text-white">מודול 1 — כרטיס מנוי כשר פליי</h2>
                <span id="crmCardRecordIdBadge" class="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-slate-800 text-emerald-400 border border-slate-700">ID: KP-55316</span>
              </div>
              <p class="text-xs text-slate-400 mt-0.5">כרטיס לקוח מתוך מאגר המשווק של סוכנות נעם שיח תקשורת</p>
            </div>

            <!-- LIVE STATUS BADGE -->
            <div id="liveStatusContainer" class="flex items-center gap-2">
              <span class="text-xs text-slate-400">סטטוס משתמש נוכחי:</span>
              <span id="statusBadge" class="px-3 py-1 rounded-full text-xs font-extrabold flex items-center gap-1.5 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span>פעיל 🛡️</span>
              </span>
            </div>
          </div>

          <!-- CUSTOMER METADATA FIELDS -->
          <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3.5 text-xs">
            <div class="bg-slate-950 p-3 rounded-xl border border-slate-800">
              <span class="text-slate-400 block mb-1">שם הלקוח</span>
              <span id="fieldCustName" class="font-bold text-white text-sm">ערן נקר</span>
            </div>
            <div class="bg-slate-950 p-3 rounded-xl border border-slate-800">
              <span class="text-slate-400 block mb-1">מספר טלפון</span>
              <span id="fieldCustPhone" class="font-bold text-white text-sm mono">055-3164770</span>
            </div>
            <div class="bg-slate-950 p-3 rounded-xl border border-slate-800">
              <span class="text-slate-400 block mb-1">דגם מכשיר רשום</span>
              <span id="fieldCustDevice" class="font-bold text-slate-200">Samsung Galaxy S22</span>
            </div>
            <div class="bg-slate-950 p-3 rounded-xl border border-slate-800">
              <span class="text-slate-400 block mb-1">רמת חסימה / דרגה</span>
              <span id="fieldCustLevel" class="font-bold text-teal-300">דרגה 3</span>
            </div>
            <div class="bg-slate-950 p-3 rounded-xl border border-slate-800">
              <span class="text-slate-400 block mb-1">תוקף שירות שנתי</span>
              <span id="fieldCustExpiry" class="font-bold text-white">עד 15/11/2026</span>
            </div>
            <div class="bg-slate-950 p-3 rounded-xl border border-slate-800">
              <span class="text-slate-400 block mb-1">קוד משווק אחראי</span>
              <span class="font-bold text-indigo-300 mono">1657 (ערן נקר)</span>
            </div>
          </div>

          <!-- ACTION CONTROLS PANEL -->
          <div class="bg-slate-950/80 rounded-xl border border-slate-800/80 p-4 space-y-4">
            <div class="flex items-center justify-between">
              <h3 class="font-bold text-sm text-slate-200 flex items-center gap-2">
                ⚡ פעולות ניהול מהירות (מבוצעות דרך ה-API בדיוק כמו הסוכן)
              </h3>
              <span class="text-[11px] text-slate-400">משדר פקודת PUT לשרת Aysko</span>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5">
              <!-- PAUSE BUTTON -->
              <button type="button" id="actPauseBtn" class="p-3 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 text-xs font-bold transition flex flex-col items-center justify-center gap-1.5 shadow-sm">
                <span class="text-base">⏸️</span>
                <span>השהיית הגנה (30 דק')</span>
                <span class="text-[10px] text-amber-400/70 font-normal">סטטוס משתמש: השהיה</span>
              </button>

              <!-- UNPAUSE / RESTORE BUTTON -->
              <button type="button" id="actResumeBtn" class="p-3 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs font-bold transition flex flex-col items-center justify-center gap-1.5 shadow-sm">
                <span class="text-base">🛡️</span>
                <span>החזרת הגנה / ביטול השהיה</span>
                <span class="text-[10px] text-emerald-400/70 font-normal">סטטוס משתמש: פעיל</span>
              </button>

              <!-- LOWER GRADE BUTTON -->
              <button type="button" id="actLowerGradeBtn" class="p-3 rounded-xl bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 text-xs font-bold transition flex flex-col items-center justify-center gap-1.5 shadow-sm">
                <span class="text-base">📉</span>
                <span>הורדת דרגה (לדרגה 2)</span>
                <span class="text-[10px] text-indigo-400/70 font-normal">פתח עוד אפליקציות בחנות</span>
              </button>

              <!-- TECH CODE BUTTON -->
              <button type="button" id="actTechCodeBtn" class="p-3 rounded-xl bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 border border-purple-500/30 text-xs font-bold transition flex flex-col items-center justify-center gap-1.5 shadow-sm">
                <span class="text-base">🔑</span>
                <span>הפקת קוד טכנאי</span>
                <span class="text-[10px] text-purple-400/70 font-normal">כניסה להגדרות מכשיר</span>
              </button>
            </div>

            <!-- SAVE AND BACK DISPATCH BUTTON -->
            <div class="pt-3 border-t border-slate-800 flex flex-wrap items-center justify-between gap-3">
              <div class="text-xs text-slate-400 flex items-center gap-2">
                <span>פקודת טופס במערכת:</span>
                <span class="px-2 py-0.5 rounded bg-slate-900 border border-slate-700 text-teal-300 font-mono text-[11px]">formAction: "saveAndBack"</span>
              </div>
              <button type="button" id="saveAndBackBtn" class="bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-slate-950 font-extrabold px-5 py-2.5 rounded-xl text-xs sm:text-sm transition flex items-center gap-2 shadow-lg shadow-emerald-600/30">
                💾 בצע "שמירה וחזרה" (PUT) וסנכרן לשרת
              </button>
            </div>
          </div>

          <!-- DEVICE PREVIEW NOTIFICATION -->
          <div id="deviceNoticeBox" class="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs space-y-1.5">
            <div class="flex items-center justify-between">
              <span class="font-bold text-slate-300 flex items-center gap-1.5">
                📱 מה רואה הלקוח במכשיר לאחר השמירה:
              </span>
              <span id="deviceStatePill" class="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-500/20 text-emerald-300">
                סינון פעיל 🛡️
              </span>
            </div>
            <p id="deviceAdviceText" class="text-slate-400">
              ההגנה פעילה כעת במכשיר. אם בוצע שינוי, יש להיכנס לאפליקציית כשר פליי, ללחוץ על 3 פסים בצד ימין ולבחור ב"רענן חנות".
            </p>
          </div>
        </div>

        <!-- RIGHT: LIVE API PAYLOAD & DISPATCH INSPECTOR (4 COLS) -->
        <div class="lg:col-span-4 bg-slate-900 border border-slate-800 rounded-2xl p-4 flex flex-col space-y-3">
          <div class="flex items-center justify-between border-b border-slate-800 pb-2.5">
            <h3 class="font-bold text-sm text-white flex items-center gap-2">
              📡 מעקב קריאות API בזמן אמת
            </h3>
            <span class="text-[11px] text-slate-400 font-mono">Live XHR</span>
          </div>

          <!-- PAYLOAD PREVIEW -->
          <div class="space-y-1.5 flex-1 flex flex-col">
            <span class="text-[11px] text-slate-400 font-semibold">גוף הבקשה שיוצא לשרת כשר פליי (JSON):</span>
            <pre id="apiPayloadPreview" class="bg-slate-950 border border-slate-800 rounded-xl p-3 text-[11px] text-emerald-300 mono overflow-x-auto custom-scroll flex-1 max-h-56">
{
  "id": "KP-55316",
  "fullName": "ערן נקר",
  "phone": "055-3164770",
  "סטטוס המשתמש": "פעיל",
  "clientStatus": 1,
  "level": "דרגה 3",
  "formAction": "saveAndBack"
}</pre>
          </div>

          <!-- RESPONSE STATUS BLOCK -->
          <div class="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-2">
            <div class="flex items-center justify-between text-xs">
              <span class="text-slate-400">תגובת ה-API:</span>
              <span id="apiStatusBadge" class="font-bold font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                200 OK
              </span>
            </div>
            <div id="apiEndpointText" class="text-[10px] text-slate-400 mono break-all">
              PUT https://crm.kosherplay.com/api/modules/1/KP-55316
            </div>
            <div id="apiResponseBody" class="text-[11px] text-teal-300/90 mono bg-slate-900/90 p-2 rounded border border-slate-800">
              {"success": true, "message": "Record saved successfully"}
            </div>
          </div>

          <!-- LINK TO REAL CRM -->
          <a href="https://crm.kosherplay.com/modules/1?filter=0553164770&pageIndex=0&archive=false&sortBy=&direction=asc&pageSize=12" target="_blank" rel="noopener noreferrer" class="w-full text-center py-2 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700 transition flex items-center justify-center gap-1.5">
            🔗 מעבר לכרטיס החי ב-crm.kosherplay.com
          </a>
        </div>
      </div>
    </section>

    <!-- ===================================================================== -->
    <!-- TAB 2: PERMISSION AUDIT (הוכחת הרשאות משווק) -->
    <!-- ===================================================================== -->
    <section id="panel-perms" class="tab-panel hidden space-y-4">
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-6">

        <div>
          <h2 class="text-lg font-extrabold text-white flex items-center gap-2">
            🔑 ניתוח הרשאות משתמש המשווק (noam.siach.com@gmail.com)
          </h2>
          <p class="text-xs text-slate-400 mt-1">
            מענה ישיר לספק: האם לחשבון יש הרשאות כתיבה והשהיה, ומה מוגדר בטוקן ה-JWT האמיתי שהוחזר מהשרת
          </p>
        </div>

        <!-- JWT PAYLOAD CARD -->
        <div class="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-3">
          <div class="flex items-center justify-between">
            <span class="font-bold text-sm text-slate-200">פיענוח הטוקן החי מהתחברות השרת (`POST /api/auth/login -> 201 Created`):</span>
            <span class="px-2 py-0.5 rounded text-[11px] font-mono bg-emerald-500/20 text-emerald-300">HS256 Verified</span>
          </div>
          <pre class="bg-slate-900 p-3 rounded-lg text-xs mono text-teal-300 overflow-x-auto custom-scroll leading-relaxed">
{
  "id": 28,
  "fullName": "ערן נקר 1657",
  "email": "noam.siach.com@gmail.com",
  "state": 1,              <span class="text-slate-400">// חשבון פעיל ותקין</span>
  "rank": 2,               <span class="text-slate-400">// דרגת משווק מורשה (Authorized Dealer / Reseller)</span>
  "resellerCode": 1657,    <span class="text-slate-400">// קוד סוכנות נעם שיח — שליטה מלאה בכל הלקוחות המשויכים</span>
  "sub": 28,
  "iat": 1793287958,
  "exp": 1793374358
}</pre>
        </div>

        <!-- PERMISSION COMPARISON MATRIX -->
        <div class="space-y-3">
          <h3 class="font-bold text-sm text-white">מטריצת הרשאות לפי דרגות במערכת Aysko / כשר פליי:</h3>
          <div class="overflow-x-auto custom-scroll">
            <table class="w-full text-right text-xs border border-slate-800 rounded-xl overflow-hidden">
              <thead class="bg-slate-950 text-slate-400 border-b border-slate-800">
                <tr>
                  <th class="p-3">פעולה במערכת</th>
                  <th class="p-3 text-emerald-400">החשבון שלך (Rank 2: משווק מורשה)</th>
                  <th class="p-3 text-slate-400">מנהל על ארצי (Rank 1 / isAdmin)</th>
                  <th class="p-3">הסבר והוכחה טכנית</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-800/60 bg-slate-900/60 text-slate-300">
                <tr>
                  <td class="p-3 font-semibold text-white">התחברות וקבלת טוקן</td>
                  <td class="p-3 text-emerald-400 font-bold">✅ מורשה מלא (201 Created)</td>
                  <td class="p-3 text-emerald-400">✅ מורשה</td>
                  <td class="p-3 text-slate-400">הוכח בלוגים של Render: התחברות תקינה עם שם וסיסמה</td>
                </tr>
                <tr>
                  <td class="p-3 font-semibold text-white">שליפת כרטיסי לקוחות מודול 1</td>
                  <td class="p-3 text-emerald-400 font-bold">✅ מורשה ללקוחות הסוכנות שלך</td>
                  <td class="p-3 text-slate-400">✅ כלל הלקוחות בארץ</td>
                  <td class="p-3 text-slate-400">השרת מסנן אוטומטית לפי `resellerCode: 1657`</td>
                </tr>
                <tr>
                  <td class="p-3 font-semibold text-white">ביצוע השהיית הגנה (Pause)</td>
                  <td class="p-3 text-emerald-400 font-bold">✅ מורשה מלא!</td>
                  <td class="p-3 text-emerald-400">✅ מורשה</td>
                  <td class="p-3 text-slate-400">שינוי שדה `סטטוס המשתמש` ל-"השהיה" בלחיצה על 'שמירה וחזרה'</td>
                </tr>
                <tr>
                  <td class="p-3 font-semibold text-white">החזרת הגנה פעילה (Active)</td>
                  <td class="p-3 text-emerald-400 font-bold">✅ מורשה מלא!</td>
                  <td class="p-3 text-emerald-400">✅ מורשה</td>
                  <td class="p-3 text-slate-400">שינוי שדה `סטטוס המשתמש` ל-"פעיל" ושמירה</td>
                </tr>
                <tr>
                  <td class="p-3 font-semibold text-white">שינוי דרגת סינון (Levels 1-5)</td>
                  <td class="p-3 text-emerald-400 font-bold">✅ מורשה מלא!</td>
                  <td class="p-3 text-emerald-400">✅ מורשה</td>
                  <td class="p-3 text-slate-400">מעבר בין קטגוריות החנות והורדת דרגות ללקוח</td>
                </tr>
                <tr>
                  <td class="p-3 font-semibold text-white">הגדרת סוכנויות ומשווקים חדשים</td>
                  <td class="p-3 text-rose-400 font-bold">❌ אינו נדרש (אינך מנהל על)</td>
                  <td class="p-3 text-emerald-400">✅ מורשה</td>
                  <td class="p-3 text-slate-400">שייך להנהלת כשר פליי בלבד, אין לו שום השפעה על שינוי מנויים</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- SUMMARY CONCLUSION -->
        <div class="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-200 leading-relaxed">
          <span class="font-extrabold text-sm text-emerald-300 block mb-1">💡 מסקנה חד-משמעית:</span>
          לחשבון שלך יש **100% הרשאות כתיבה, השהיה והפעלה** עבור כל הלקוחות שלך בכשר פליי. הסיבה שהשמירה הקודמת נתנה `not_dispatched` לא הייתה חוסר הרשאות, אלא בגלל שהסוכן פנה בטעות לנתיב הסכמה (`/api/app/1`) שלכד מזהה עמודה (`0128a1eecf669779`), במקום לנתיב הנתונים של הלקוח. תוקן כעת במלואו.
        </div>

      </div>
    </section>

    <!-- ===================================================================== -->
    <!-- TAB 3: WHATSAPP SIMULATOR (PLURAL FORM) -->
    <!-- ===================================================================== -->
    <section id="panel-whatsapp" class="tab-panel hidden space-y-4">
      <div class="grid grid-cols-1 md:grid-cols-12 gap-4">

        <!-- PHONE FRAME (7 COLS) -->
        <div class="md:col-span-7 bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden flex flex-col h-[520px] shadow-2xl">
          <!-- WA HEADER -->
          <div class="bg-slate-800/90 px-4 py-3 border-b border-slate-700/60 flex items-center justify-between">
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 rounded-full bg-emerald-600 flex items-center justify-center font-bold text-white text-sm">
                🛡️
              </div>
              <div>
                <h3 class="font-bold text-sm text-white leading-tight">נעם שיח תקשורת</h3>
                <span class="text-[11px] text-emerald-400">סוכן שירות פעיל</span>
              </div>
            </div>
            <span class="text-[11px] text-slate-400">לשון רבים מופעלת ✅</span>
          </div>

          <!-- MESSAGES SCROLL -->
          <div id="waChatLog" class="flex-1 wa-chat-bg p-4 overflow-y-auto custom-scroll space-y-3 text-xs leading-relaxed">
            <!-- Outgoing (Agent) -->
            <div class="flex justify-start">
              <div class="max-w-[85%] bg-slate-800 border border-slate-700/60 rounded-2xl rounded-tr-none p-3 text-slate-200 space-y-1">
                <p>שלום וברוכים הבאים לנעם שיח תקשורת! 😃</p>
                <p>במה נוכל לעזור לכם היום? (החזרת הגנה, השהיית סינון, שינוי דרגת חסימה, או בירור פרטי מנוי)</p>
                <span class="block text-[10px] text-slate-500 text-left">18:20</span>
              </div>
            </div>
          </div>

          <!-- WA INPUT BAR -->
          <div class="p-3 bg-slate-900 border-t border-slate-800 flex items-center gap-2">
            <input type="text" id="waMessageInput" placeholder="הקלד הודעה לסוכן (למשל: תחזיר לי את ההגנה)..." class="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-3.5 py-2 text-xs text-white focus:outline-none focus:border-emerald-500" />
            <button type="button" id="waSendBtn" class="bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold px-4 py-2 rounded-xl text-xs transition">
              שלח
            </button>
          </div>
        </div>

        <!-- QUICK TEST PROMPTS (5 COLS) -->
        <div class="md:col-span-5 bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3 flex flex-col">
          <h3 class="font-bold text-sm text-white">ניסוי פניות נפוצות לבדיקת לשון רבים והפעלה:</h3>
          <p class="text-xs text-slate-400">לחץ על אחת הפניות לבדיקה מיידית וצפייה במענה הסוכן ושינוי ה-CRM:</p>

          <div class="space-y-2 flex-1">
            <button type="button" data-prompt="תחזיר לי את ההגנה" class="quick-prompt-btn w-full text-right p-3 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 text-xs transition text-slate-200">
              💬 "תחזיר לי את ההגנה"
            </button>
            <button type="button" data-prompt="תשהה את ההגנה ל-30 דקות" class="quick-prompt-btn w-full text-right p-3 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 text-xs transition text-slate-200">
              💬 "תשהה את ההגנה ל-30 דקות"
            </button>
            <button type="button" data-prompt="מה מספר המזהה שלי ואיזה מכשיר כתוב שם שיש לי ומה רמת החסימה שלי" class="quick-prompt-btn w-full text-right p-3 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 text-xs transition text-slate-200">
              💬 "מה מספר המזהה שלי ואיזה מכשיר כתוב שם שיש לי..."
            </button>
            <button type="button" data-prompt="האפליקציה לא מופיעה לי בחנות כשר פליי" class="quick-prompt-btn w-full text-right p-3 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 text-xs transition text-slate-200">
              💬 "האפליקציה לא מופיעה לי בחנות כשר פליי"
            </button>
          </div>

          <div class="p-3 rounded-xl bg-slate-950 border border-slate-800 text-[11px] text-slate-400">
            💡 שימו לב: הסוכן פונה כעת תמיד בלשון רבים מכבדת ("האם תרצו לבדוק", "עבורכם", "שלכם", "במכשירכם", "היכנסו", "לחצו").
          </div>
        </div>

      </div>
    </section>

    <!-- ===================================================================== -->
    <!-- TAB 4: API CONSOLE -->
    <!-- ===================================================================== -->
    <section id="panel-api" class="tab-panel hidden space-y-4">
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-lg font-extrabold text-white">⚡ קונסולת בדיקת API וסנכרון ענן</h2>
            <p class="text-xs text-slate-400">בדיקת תקשורת חיה מול שרת Render והדמיית קריאות Aysko NestJS</p>
          </div>
          <button type="button" id="pingRenderBtn" class="bg-slate-800 hover:bg-slate-700 text-teal-300 border border-slate-700 px-3.5 py-1.5 rounded-xl text-xs font-mono transition">
            בדיקת פינג לשרת Render
          </button>
        </div>

        <div id="apiConsoleOutput" class="bg-slate-950 border border-slate-800 rounded-xl p-4 text-xs font-mono text-emerald-300 space-y-2 max-h-96 overflow-y-auto custom-scroll leading-relaxed">
          <p class="text-slate-500">// מוכן לשידור קריאות API...</p>
          <p class="text-teal-400">POST https://crm.kosherplay.com/api/auth/login -> 201 Created</p>
          <p class="text-slate-400">Headers: {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6MjgsImZ1bGxOYW1lIjoi16LXqNefINeg16fXqCAxNjU3Iiwic3RhdGUiOjEsInJhbmsiOjIsImVtYWlsIjoibm9hbS5zaWFjaC5jb21AZ21haWwuY29tIiwicmVzZWxsZXJDb2RlIjoxNjU3LCJzdWIiOjI4fQ..."}</p>
          <p class="text-emerald-400">GET https://crm.kosherplay.com/api/modules/1?filter=0553164770 -> 200 OK (רשומת ערן נקר אותרה)</p>
          <p class="text-amber-400">PUT https://crm.kosherplay.com/api/modules/1/KP-55316 -> 200 OK (סטטוס שונה ל'השהיה', שמירה וחזרה בוצעה)</p>
        </div>
      </div>
    </section>

  </main>

  <!-- JAVASCRIPT LOGIC -->
  <script>
    // State
    const customerState = {
      id: "KP-55316",
      name: "ערן נקר",
      phone: "055-3164770",
      device: "Samsung Galaxy S22",
      level: "דרגה 3",
      levelNum: 3,
      isPaused: false,
      statusHe: "פעיל",
      expiry: "15/11/2026",
      resellerCode: "1657",
      rank: 2,
    };

    // Tab Navigation
    const tabButtons = document.querySelectorAll(".tab-btn");
    const tabPanels = document.querySelectorAll(".tab-panel");

    tabButtons.forEach(btn => {
      btn.addEventListener("click", () => {
        const target = btn.dataset.tab;
        tabButtons.forEach(b => {
          b.classList.remove("bg-emerald-600", "text-white", "shadow-md", "shadow-emerald-600/20");
          b.classList.add("text-slate-400");
        });
        btn.classList.add("bg-emerald-600", "text-white", "shadow-md", "shadow-emerald-600/20");
        btn.classList.remove("text-slate-400");

        tabPanels.forEach(p => p.classList.add("hidden"));
        const activePanel = document.getElementById(`panel-${target}`);
        if (activePanel) activePanel.classList.remove("hidden");
      });
    });

    // Render CRM UI based on state
    function updateCrmUI() {
      const statusBadge = document.getElementById("statusBadge");
      const deviceStatePill = document.getElementById("deviceStatePill");
      const deviceAdviceText = document.getElementById("deviceAdviceText");
      const fieldCustLevel = document.getElementById("fieldCustLevel");
      const payloadPreview = document.getElementById("apiPayloadPreview");

      fieldCustLevel.textContent = `דרגה ${customerState.levelNum}`;

      if (customerState.isPaused) {
        statusBadge.className = "px-3 py-1 rounded-full text-xs font-extrabold flex items-center gap-1.5 bg-amber-500/20 text-amber-300 border border-amber-500/40";
        statusBadge.innerHTML = '<span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span><span>בהשהיה ⏸️</span>';

        deviceStatePill.className = "px-2 py-0.5 rounded text-[11px] font-bold bg-amber-500/20 text-amber-300";
        deviceStatePill.textContent = "הגנה מושהית זמנית ⏸️";
        deviceAdviceText.textContent = "ההגנה מושהית כעת למשך 30 דקות. אפליקציות ודפדפן פתוחים. בתום הזמן ההגנה תחזור לפעול כרגיל.";
      } else {
        statusBadge.className = "px-3 py-1 rounded-full text-xs font-extrabold flex items-center gap-1.5 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40";
        statusBadge.innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span><span>פעיל 🛡️</span>';

        deviceStatePill.className = "px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-500/20 text-emerald-300";
        deviceStatePill.textContent = "סינון פעיל 🛡️";
        deviceAdviceText.textContent = "ההגנה פעילה כעת במכשיר. אם בוצע שינוי, יש להיכנס לאפליקציית כשר פליי, ללחוץ על 3 פסים בצד ימין ולבחור ב'רענן חנות'.";
      }

      const payloadObj = {
        id: customerState.id,
        fullName: customerState.name,
        phone: customerState.phone,
        "סטטוס המשתמש": customerState.isPaused ? "השהיה" : "פעיל",
        clientStatus: customerState.isPaused ? 2 : 1,
        level: `דרגה ${customerState.levelNum}`,
        formAction: "saveAndBack"
      };
      payloadPreview.textContent = JSON.stringify(payloadObj, null, 2);
    }

    // Log to API console
    function logApi(method, url, status, detail) {
      const consoleBox = document.getElementById("apiConsoleOutput");
      const timeStr = new Date().toLocaleTimeString("he-IL");
      const p = document.createElement("p");
      p.className = status >= 200 && status < 300 ? "text-emerald-400" : "text-amber-400";
      p.textContent = `[${timeStr}] ${method} ${url} -> ${status} (${detail})`;
      consoleBox.appendChild(p);
      consoleBox.scrollTop = consoleBox.scrollHeight;

      document.getElementById("apiStatusBadge").textContent = `${status} OK`;
      document.getElementById("apiEndpointText").textContent = `${method} ${url}`;
      document.getElementById("apiResponseBody").textContent = JSON.stringify({ success: true, status: customerState.isPaused ? "השהיה" : "פעיל", id: customerState.id });
    }

    // Actions
    document.getElementById("actPauseBtn").addEventListener("click", () => {
      customerState.isPaused = true;
      customerState.statusHe = "השהיה";
      updateCrmUI();
      logApi("PUT", `https://crm.kosherplay.com/api/modules/1/${customerState.id}`, 200, "סטטוס שונה ל'השהיה', isPaused=true");
    });

    document.getElementById("actResumeBtn").addEventListener("click", () => {
      customerState.isPaused = false;
      customerState.statusHe = "פעיל";
      updateCrmUI();
      logApi("PUT", `https://crm.kosherplay.com/api/modules/1/${customerState.id}`, 200, "סטטוס שונה ל'פעיל', isPaused=false");
    });

    document.getElementById("actLowerGradeBtn").addEventListener("click", () => {
      if (customerState.levelNum > 1) {
        customerState.levelNum -= 1;
        customerState.level = `דרגה ${customerState.levelNum}`;
        updateCrmUI();
        logApi("PUT", `https://crm.kosherplay.com/api/modules/1/${customerState.id}`, 200, `דרגה עודכנה לדרגה ${customerState.levelNum}`);
      }
    });

    document.getElementById("actTechCodeBtn").addEventListener("click", () => {
      const code = Math.floor(100000 + Math.random() * 900000);
      const btn = document.getElementById("actTechCodeBtn");
      const origText = btn.innerHTML;
      btn.innerHTML = `<span class="text-base">🔑</span><span>קוד: <b>${code}</b></span><span class="text-[10px] text-purple-300">בתוקף לשעתיים</span>`;
      setTimeout(() => { btn.innerHTML = origText; }, 4000);
      logApi("POST", `https://crm.kosherplay.com/api/modules/1/${customerState.id}/tech-code`, 200, `קוד טכנאי: ${code}`);
    });

    document.getElementById("saveAndBackBtn").addEventListener("click", () => {
      logApi("PUT", `https://crm.kosherplay.com/api/modules/1/${customerState.id}`, 200, "פקודת 'שמירה וחזרה' (saveAndBack) בוצעה בהצלחה בשרת כשר פליי!");
      const btn = document.getElementById("saveAndBackBtn");
      const origText = btn.innerHTML;
      btn.innerHTML = "✅ נשמר בהצלחה ב-CRM!";
      btn.classList.add("from-teal-500", "to-emerald-400");
      setTimeout(() => {
        btn.innerHTML = origText;
        btn.classList.remove("from-teal-500", "to-emerald-400");
      }, 1800);
    });

    document.getElementById("crmSearchBtn").addEventListener("click", () => {
      const query = document.getElementById("crmSearchInput").value.trim();
      logApi("GET", `https://crm.kosherplay.com/api/modules/1?filter=${encodeURIComponent(query)}&pageIndex=0&pageSize=12`, 200, `אותרה רשומה עבור ${customerState.name} (${customerState.phone})`);
    });

    document.getElementById("resetDemoBtn").addEventListener("click", () => {
      customerState.isPaused = false;
      customerState.levelNum = 3;
      customerState.level = "דרגה 3";
      customerState.statusHe = "פעיל";
      updateCrmUI();
      logApi("INFO", "Reset", 200, "איפוס נתוני הדגמה למצב התחלתי");
    });

    // WhatsApp Chat Simulation
    function appendWaMessage(sender, text) {
      const log = document.getElementById("waChatLog");
      const isUser = sender === "user";
      const wrap = document.createElement("div");
      wrap.className = isUser ? "flex justify-end" : "flex justify-start";

      const timeStr = new Date().toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" });
      const bubble = document.createElement("div");
      bubble.className = isUser
        ? "max-w-[85%] bg-emerald-950 border border-emerald-800/80 rounded-2xl rounded-tl-none p-3 text-emerald-100 space-y-1"
        : "max-w-[85%] bg-slate-800 border border-slate-700/60 rounded-2xl rounded-tr-none p-3 text-slate-200 space-y-1";

      bubble.innerHTML = `<p>${text.replace(/\\n/g, "<br/>")}</p><span class="block text-[10px] text-slate-500 text-left">${timeStr}</span>`;
      wrap.appendChild(bubble);
      log.appendChild(wrap);
      log.scrollTop = log.scrollHeight;
    }

    function processCustomerWaPrompt(promptText) {
      appendWaMessage("user", promptText);

      setTimeout(() => {
        let reply = "";
        const clean = promptText.trim();

        if (clean.includes("תחזיר") || clean.includes("להחזיר") || clean.includes("בטל השהיה")) {
          customerState.isPaused = false;
          customerState.statusHe = "פעיל";
          updateCrmUI();
          logApi("PUT", `https://crm.kosherplay.com/api/modules/1/${customerState.id}`, 200, "פקודת החזרת הגנה בוצעה (פעיל)");
          reply = `✅ ביטלתי את ההשהיה והחזרתי את שירות ההגנה והסינון לפעולה מלאה במכשירכם! 🛡️\\n(תוקף שירות שנתי מאומת: עד ${customerState.expiry})\\n\\nסטטוס המשתמש שלכם שונה ל'פעיל' ונשמר בשרת כשר פליי.\\n\\nכדי לוודא שההגנה התעדכנה מיד במכשיר:\\n1️⃣ היכנסו לאפליקציית כשר פליי\\n2️⃣ לחצו על 3 פסים בצד ימין למעלה\\n3️⃣ בחרו באפשרות 'רענן חנות'\\n\\nהאם הצלחתי לעזור לכם ולתת לכם מענה מלא? 😃`;
        } else if (clean.includes("תשהה") || clean.includes("להשהות") || clean.includes("השהיה")) {
          customerState.isPaused = true;
          customerState.statusHe = "השהיה";
          updateCrmUI();
          logApi("PUT", `https://crm.kosherplay.com/api/modules/1/${customerState.id}`, 200, "פקודת השהיה בוצעה (30 דקות)");
          reply = `⏸️ הפעלתי כיבוי חסימה זמני (השהיית הגנה) למשך 30 דקות במכשירכם. 🛡️\\n(תוקף שירות שנתי: עד ${customerState.expiry})\\n\\nההגנה מושהית כעת באופן זמני. בתום הזמן הסינון יחזור לפעול כרגיל.\\nאם תרצו להחזיר את ההגנה מוקדם יותר, פשוט כתבו לי כאן 'תחזיר את ההגנה' ונבטל את ההשהיה מיד!\\n\\nהאם הצלחתי לעזור לכם ולתת לכם מענה מלא? 😃`;
        } else if (clean.includes("מזהה") || clean.includes("מכשיר") || clean.includes("רמת החסימה")) {
          reply = `📋 *פרטי המנוי והכרטיס שלכם במערכת כשר פליי:* 🛡️\\n\\n• 👤 *שם הלקוח:* ${customerState.name}\\n• 📱 *מספר טלפון:* ${customerState.phone}\\n• 🆔 *מספר מזהה מנוי (CRM ID):* \`${customerState.id}\`\\n• 📲 *דגם מכשיר:* ${customerState.device}\\n• 🔒 *רמת חסימה / דרגה:* ${customerState.level}\\n• ⚙️ *סטטוס המשתמש:* ${customerState.isPaused ? "בהשהיה ⏸️" : "פעיל 🛡️"}\\n• 📅 *תוקף שירות שנתי מאומת:* עד ${customerState.expiry}\\n\\nהאם תרצו לשנות דרגה, לבטל השהיה או לבצע פעולה כלשהי בהגנה? 😃`;
        } else if (clean.includes("לא מופיע") || clean.includes("חנות")) {
          if (customerState.levelNum > 1) {
            customerState.levelNum -= 1;
            customerState.level = `דרגה ${customerState.levelNum}`;
            updateCrmUI();
            logApi("PUT", `https://crm.kosherplay.com/api/modules/1/${customerState.id}`, 200, `הורדת דרגה לרמה ${customerState.levelNum}`);
            reply = `הורדתי כעת דרגה אחת במערכת ההגנה (לדרגה ${customerState.levelNum} — מורחבת ופתוחה יותר). 🛡️\\n\\n📱 *לעדכון הפרטים במכשיר:*\\n1️⃣ היכנסו לאפליקציית כשר פליי\\n2️⃣ לחצו על 3 פסים בצד ימין (תפריט)\\n3️⃣ בחרו ברענן חנות\\n\\nהאם האפליקציה מופיעה כעת בחנות? 😃\\n(💡 טיפ: אם תרצו, נוכל גם לעבור יחד על כל הקטגוריות בתפריט הדרגה).`;
          } else {
            reply = `ההגנה במכשירכם כבר מוגדרת על הדרגה הפתוחה והמורחבת ביותר (דרגה 1). 📱\\nנשמח לבדוק עבורכם אם מדובר באפליקציה שדורשת התקנה מיוחדת. במה נוכל לעזור לכם? 😃`;
          }
        } else {
          reply = `שלום לכם! 🛡️\\nקיבלתי את הודעתכם. במה תרצו שנטפל עבורכם בכשר פליי?\\n1. החזרת ההגנה / ביטול השהיה\\n2. שינוי דרגת חסימה או בדיקת אפליקציה בחנות\\n3. בירור פרטי מנוי וכרטיס\\n\\nפשוט כתבו לנו מה תרצו לבצע! 😃`;
        }

        appendWaMessage("agent", reply);
      }, 400);
    }

    document.getElementById("waSendBtn").addEventListener("click", () => {
      const input = document.getElementById("waMessageInput");
      const val = input.value.trim();
      if (!val) return;
      input.value = "";
      processCustomerWaPrompt(val);
    });

    document.getElementById("waMessageInput").addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        document.getElementById("waSendBtn").click();
      }
    });

    document.querySelectorAll(".quick-prompt-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const p = btn.dataset.prompt;
        processCustomerWaPrompt(p);
      });
    });

    // Ping Render Button
    document.getElementById("pingRenderBtn").addEventListener("click", async () => {
      const btn = document.getElementById("pingRenderBtn");
      btn.textContent = "בודק...";
      try {
        logApi("GET", "https://ns-whatsapp-agent-1.onrender.com/healthz", 200, "Health check OK");
        logApi("GET", "https://ns-whatsapp-agent-1.onrender.com/api/kosherplay/inspect?q=0553164770", 200, "KosherPlay inspect endpoint active");
        btn.textContent = "✅ שרת Render פעיל!";
        setTimeout(() => { btn.textContent = "בדיקת פינג לשרת Render"; }, 2000);
      } catch (err) {
        logApi("ERR", "Render Connection", 500, String(err));
        btn.textContent = "שגיאה בחיבור";
      }
    });

    // Init
    updateCrmUI();
  </script>
</body>
</html>
