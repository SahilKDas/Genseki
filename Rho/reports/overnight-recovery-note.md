# Overnight Recovery

Original campaign: campaign-1791159602857541300. Its Unix-nanosecond ID
fixes the original eight-hour window; recovery must not restart that clock.

The runner stopped after 729.25 seconds with `move search deadline` during
self-play. Four complete games were retained, bringing replay totals to
16 games and 1,391 positions. No champion promotion occurred. The report
records a minimum of 3,134,316,544 available RAM bytes, not a RAM-floor stop.

Recovery raises only the self-play move watchdog from 30 to 120 seconds
to accommodate slow full-width 64-simulation searches at Idle priority.
Simulation count, two workers, protocol timeout, memory limits, and the
original campaign deadline remain unchanged. This is a watchdog adjustment,
not a demonstrated search-performance fix. Original logs remain untouched;
recovery logs use separate filenames. A repeated timeout requires further
diagnosis rather than another identical restart.
