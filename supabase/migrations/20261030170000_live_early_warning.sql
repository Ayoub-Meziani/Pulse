-- M9 live_early_warning: the live ring engine (ml/pulse_ml/live.py, live-v1) warns the DOCTOR before a limit is
-- crossed. Advisory only, like every wearable_flags row: no safety rule reads this table (R-RING-1 and the symptom
-- rules stay in the backend), patients cannot read it (decision M4), the doctor reviews it like the other flags.
--   kind 'early_warning' + window_kind 'forecast': window_start = minute the warning was made, window_end = +20 min;
--     value = forecast at +20 min, score = P(limit crossed within 20 min), reference_basis = the limit used.
--   metric 'sleep': "this night is going badly" (P restless night), only as an early warning; once per night
--     (window_start = local midnight, so the existing unique index dedups it).
-- Additive: widens three CHECK lists and adds two consistency checks. No row, grant, policy or index changes.
alter table public.wearable_flags
  drop constraint wearable_flags_kind_check,
  add constraint wearable_flags_kind_check
    check (kind in ('outside_reference', 'personal_anomaly', 'multivariate_anomaly', 'early_warning')),
  drop constraint wearable_flags_window_kind_check,
  add constraint wearable_flags_window_kind_check check (window_kind in ('live_10min', 'night', 'forecast')),
  drop constraint wearable_flags_metric_check,
  add constraint wearable_flags_metric_check
    check (metric in ('heart_rate', 'hrv_rmssd', 'spo2', 'skin_temperature', 'multivariate', 'sleep')),
  add constraint wearable_flags_forecast_check check ((kind = 'early_warning') = (window_kind = 'forecast')),
  add constraint wearable_flags_sleep_check check (metric <> 'sleep' or kind = 'early_warning');
