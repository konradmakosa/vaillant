// Pressure trend analysis — daily minimum pressure (≈ cold-system pressure)
// and per-segment leak-rate regression. Pure functions, no DOM/Chart.js deps.
(function (global) {
    const TZ = 'Europe/Warsaw';
    const DAY_MS = 86400000;

    function dayMs(day) {
        const [y, m, d] = day.split('-').map(Number);
        return Date.UTC(y, m - 1, d);
    }

    // rows: { _ts: Date (UTC instant), water_pressure_bar: string|number|null }
    // Returns sorted [{ day: 'YYYY-MM-DD', min, n }] for days with n >= 3.
    function dailyMinimums(rows) {
        const byDay = {};
        for (const r of rows) {
            if (!(r._ts instanceof Date) || isNaN(r._ts)) continue;
            const p = parseFloat(r.water_pressure_bar);
            if (!isFinite(p)) continue;
            const day = r._ts.toLocaleDateString('sv-SE', { timeZone: TZ });
            const e = byDay[day] || (byDay[day] = { day, min: Infinity, max: -Infinity, n: 0 });
            if (p < e.min) e.min = p;
            if (p > e.max) e.max = p;
            e.n++;
        }
        return Object.values(byDay)
            .filter(d => d.n >= 3)
            .map(d => ({ ...d, swing: +(d.max - d.min).toFixed(2) }))
            .sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : 0));
    }

    // Parses events.csv -> [{ ts: Date(UTC), type, before, after, note, day }]
    function parseEvents(text) {
        const events = [];
        for (const line of String(text || '').split('\n')) {
            const t = line.trim();
            if (!t || t.startsWith('timestamp_utc')) continue;
            const parts = t.split(',');
            if (parts.length < 4) continue;
            const ts = new Date(parts[0].trim() + 'Z');
            if (isNaN(ts)) continue;
            const num = v => (v === '' || v == null ? null : parseFloat(v));
            events.push({
                ts,
                type: (parts[1] || '').trim(),
                before: num((parts[2] || '').trim()),
                after: num((parts[3] || '').trim()),
                note: parts.slice(4).join(',').trim(),
                day: ts.toLocaleDateString('sv-SE', { timeZone: TZ }),
            });
        }
        return events;
    }

    // Splits daily minimums into segments; a jump up of >= 0.5 bar = top-up.
    // manualTopUpDays: 'YYYY-MM-DD' (Warsaw) — forces a new segment at the first
    // daily-min entry AFTER that day (the event day keeps its pre-refill minimum).
    function segments(dailyMins, manualTopUpDays = []) {
        const autoIdx = new Set();
        for (let i = 1; i < dailyMins.length; i++) {
            if (dailyMins[i].min - dailyMins[i - 1].min >= 0.5) autoIdx.add(i);
        }
        // manual event on day D: covered if an auto boundary already sits on the
        // first day >= D; otherwise force a split at the first day > D
        const forced = new Set();
        const coincident = new Set();
        for (const D of manualTopUpDays) {
            const j = dailyMins.findIndex(d => d.day >= D);
            if (j > 0 && autoIdx.has(j)) { coincident.add(j); continue; }
            const k = dailyMins.findIndex(d => d.day > D);
            if (k > 0) forced.add(k);
        }
        const segs = [];
        dailyMins.forEach((d, i) => {
            const last = segs.length ? segs[segs.length - 1].days : null;
            const boundary = autoIdx.has(i) || forced.has(i);
            if (last && boundary) {
                segs.push({ days: [], topUp: true, manual: forced.has(i) || coincident.has(i) });
            }
            if (!segs.length) segs.push({ days: [], topUp: false, manual: false });
            segs[segs.length - 1].days.push(d);
        });
        for (const s of segs) {
            s.start = s.days[0].day;
            s.end = s.days[s.days.length - 1].day;
            s.startMin = s.days[0].min;
            s.endMin = s.days[s.days.length - 1].min;
            s.spanDays = (dayMs(s.end) - dayMs(s.start)) / DAY_MS;
            s.belowOneCount = s.days.filter(d => d.min < 1.0).length;
            const n = s.days.length;
            if (n < 2) {
                s.slopePerDay = 0;
                s.intercept = s.startMin;
            } else {
                const x0 = dayMs(s.start);
                const xs = s.days.map(d => (dayMs(d.day) - x0) / DAY_MS);
                const ys = s.days.map(d => d.min);
                const mx = xs.reduce((a, b) => a + b, 0) / n;
                const my = ys.reduce((a, b) => a + b, 0) / n;
                let sxx = 0, sxy = 0;
                for (let i = 0; i < n; i++) {
                    sxx += (xs[i] - mx) * (xs[i] - mx);
                    sxy += (xs[i] - mx) * (ys[i] - my);
                }
                s.slopePerDay = sxx ? sxy / sxx : 0;
                s.intercept = my - s.slopePerDay * mx;
            }
        }
        return segs;
    }

    // Segments with >= 2 days — these are what the summary table shows.
    function summary(segs) {
        return segs.filter(s => s.days.length >= 2);
    }

    // Stats over daily swing (max - min) values; null if no days.
    function swingStats(dailyMins) {
        const vals = dailyMins.map(d => d.swing).sort((a, b) => a - b);
        const n = vals.length;
        if (!n) return null;
        const median = n % 2 ? vals[(n - 1) / 2] : (vals[n / 2 - 1] + vals[n / 2]) / 2;
        return { median, p90: vals[Math.floor(0.9 * n)], max: vals[n - 1], count: n };
    }

    const api = { dailyMinimums, segments, summary, swingStats, parseEvents };
    global.PressureAnalysis = api;
    if (typeof module !== 'undefined') module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
