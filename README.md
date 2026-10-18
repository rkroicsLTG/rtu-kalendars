# RTU nodarbību kalendārs (iCal)

Automātiski ik pēc 2 stundām nolasa [nodarbibas.rtu.lv](https://nodarbibas.rtu.lv/) grafiku
(RTU Rēzeknes akadēmija, Lāzertehnoloģijas ENML0, 1. kurss, 1. grupa) un publicē to kā `.ics` failu GitHub Pages.

**Abonēšanas saite:** `https://<lietotājs>.github.io/rtu-kalendars/rtu.ics`

## iPhone
Iestatījumi → Kalendārs → Konti → Pievienot kontu → Cits → **Pievienot abonētu kalendāru** → ielīmē saiti
(var rakstīt `webcal://` `https://` vietā). Atjaunošanas biežums: Iestatījumi → Kalendārs → Konti → Ielādēt jaunus datus.

## Google kalendārs
calendar.google.com → Citi kalendāri → „+” → **No URL** → ielīmē saiti.

## Iestatījumi
`.github/workflows/update.yml` → `RTU_COURSE`, `RTU_GROUP`, `RTU_PROGRAM_ID`.
Jaunā semestra grafiks tiek paņemts automātiski, tiklīdz RTU to publicē.
Nākamajā mācību gadā nomaini `RTU_COURSE` uz `2`.

Manuāla atjaunošana: cilne **Actions** → „Atjaunot RTU kalendāru” → **Run workflow**.
