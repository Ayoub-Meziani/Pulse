-- PULSE schema-only export (structure, keys, indexes, triggers, RLS policies, grants). NO DATA.
-- Generated 2026-10-30 from the LOCAL Supabase stack with:
--   pg_dump --schema-only --no-owner --schema=public --schema=private
-- Authoritative source remains supabase/migrations/ (apply those with `supabase db push`, not this file).
-- auth.* is Supabase-managed and not dumped; PULSE adds only the trigger at the end of this file.

--
-- PostgreSQL database dump
--


-- Dumped from database version 17.11
-- Dumped by pg_dump version 17.11

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: private; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA private;


--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: audit(); Type: FUNCTION; Schema: private; Owner: -
--

CREATE FUNCTION private.audit() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
begin
  insert into public.audit_log (table_name, row_id, action, actor, old_data, new_data)
  values (tg_table_name,
          case when tg_op = 'DELETE' then old.id else new.id end,
          tg_op, auth.uid(),
          case when tg_op <> 'INSERT' then to_jsonb(old) end,
          case when tg_op <> 'DELETE' then to_jsonb(new) end);
  return case when tg_op = 'DELETE' then old else new end;
end $$;


--
-- Name: can_read_patient(uuid); Type: FUNCTION; Schema: private; Owner: -
--

CREATE FUNCTION private.can_read_patient(patient uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO ''
    AS $$
  select patient = auth.uid() or private.is_assigned_doctor(patient) or private.current_app_role() = 'admin'
$$;


--
-- Name: current_app_role(); Type: FUNCTION; Schema: private; Owner: -
--

CREATE FUNCTION private.current_app_role() RETURNS text
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO ''
    AS $$
  select role from public.profiles where id = auth.uid()
$$;


--
-- Name: enforce_roles(); Type: FUNCTION; Schema: private; Owner: -
--

CREATE FUNCTION private.enforce_roles() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
declare
  i int := 0;
  uid uuid;
  got text;
begin
  while i < tg_nargs loop
    uid := (to_jsonb(new) ->> tg_argv[i])::uuid;
    if uid is not null then
      select role into got from public.profiles where id = uid;
      if got is distinct from tg_argv[i + 1] then
        raise exception '%.% must reference a % profile', tg_table_name, tg_argv[i], tg_argv[i + 1]
          using errcode = '23514';
      end if;
    end if;
    i := i + 2;
  end loop;
  return new;
end $$;


--
-- Name: handle_new_user(); Type: FUNCTION; Schema: private; Owner: -
--

CREATE FUNCTION private.handle_new_user() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(nullif(trim(new.raw_user_meta_data ->> 'display_name'), ''),
                           split_part(coalesce(new.email, 'user'), '@', 1)));
  return new;
end $$;


--
-- Name: is_assigned_doctor(uuid); Type: FUNCTION; Schema: private; Owner: -
--

CREATE FUNCTION private.is_assigned_doctor(patient uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO ''
    AS $$
  select exists (select 1 from public.doctor_patient_assignments a
                 where a.doctor_id = auth.uid() and a.patient_id = patient and a.status = 'active')
$$;


--
-- Name: is_my_doctor(uuid); Type: FUNCTION; Schema: private; Owner: -
--

CREATE FUNCTION private.is_my_doctor(doctor uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO ''
    AS $$
  select exists (select 1 from public.doctor_patient_assignments a
                 where a.patient_id = auth.uid() and a.doctor_id = doctor and a.status = 'active')
$$;


--
-- Name: is_valid_tz(text); Type: FUNCTION; Schema: private; Owner: -
--

CREATE FUNCTION private.is_valid_tz(tz text) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE
    SET search_path TO ''
    AS $$
begin
  perform timestamptz '2000-01-01 00:00+00' at time zone tz;
  return true;
exception when others then
  return false;
end $$;


--
-- Name: touch_updated_at(); Type: FUNCTION; Schema: private; Owner: -
--

CREATE FUNCTION private.touch_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
begin
  new.updated_at := now();
  return new;
end $$;


--
-- Name: validate_measurement(); Type: FUNCTION; Schema: private; Owner: -
--

CREATE FUNCTION private.validate_measurement() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
declare
  hard text[] := '{}';
  soft text[] := coalesce(new.quality_flags, '{}');
begin
  if new.systolic <= new.diastolic then hard := array_append(hard, 'systolic_not_above_diastolic'); end if;
  if new.systolic not between 50 and 300 then hard := array_append(hard, 'systolic_implausible'); end if;
  if new.diastolic not between 25 and 200 then hard := array_append(hard, 'diastolic_implausible'); end if;
  if new.pulse not between 25 and 250 then hard := array_append(hard, 'pulse_implausible'); end if;
  if new.measured_at > now() + interval '5 minutes' then hard := array_append(hard, 'measured_in_future'); end if;

  if new.systolic not between 70 and 250 or new.diastolic not between 40 and 150 then
    soft := array_append(soft, 'unusual_value_recheck');
  end if;
  if new.provenance = 'estimated' then soft := array_append(soft, 'estimated_not_cuff'); end if;
  -- ponytail: misses two identical inserts racing in parallel; fine for manual entry
  if exists (
    select 1 from public.measurements m
    where m.patient_id = new.patient_id and m.id <> new.id
      and m.systolic = new.systolic and m.diastolic = new.diastolic
      and m.pulse is not distinct from new.pulse
      and m.measured_at between new.measured_at - interval '2 minutes' and new.measured_at + interval '2 minutes'
  ) then
    soft := array_append(soft, 'possible_duplicate');
  end if;

  new.quality_flags := array(select distinct f from unnest(hard || soft) f order by f);
  new.validation_status := case
    when cardinality(hard) > 0 then 'invalid'
    when cardinality(new.quality_flags) > 0 then 'needs_review'
    else 'valid' end;
  new.validation_policy_version := 'pulse-v1';
  new.created_by := coalesce(auth.uid(), new.created_by);
  return new;
end $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alert_measurements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_measurements (
    alert_id uuid NOT NULL,
    measurement_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    attached_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alerts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    patient_id uuid NOT NULL,
    measurement_id uuid,
    symptom_report_id uuid,
    alert_class text NOT NULL,
    trigger_source text DEFAULT 'rule_engine'::text NOT NULL,
    rule_code text NOT NULL,
    rule_version text,
    reason text NOT NULL,
    actions text[] DEFAULT '{}'::text[] NOT NULL,
    status text DEFAULT 'open'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    acknowledged_at timestamp with time zone,
    acknowledged_by uuid,
    reviewed_at timestamp with time zone,
    reviewed_by uuid,
    resolved_at timestamp with time zone,
    resolved_by uuid,
    resolution_note text,
    persistent boolean DEFAULT false NOT NULL,
    CONSTRAINT alerts_alert_class_check CHECK ((alert_class = ANY (ARRAY['routine'::text, 'above_target'::text, 'above_target_trend'::text, 'severely_high'::text, 'possible_emergency'::text, 'follow_up'::text, 'lifestyle_review'::text, 'data_quality_review'::text]))),
    CONSTRAINT alerts_check CHECK (((status <> 'acknowledged'::text) OR (acknowledged_at IS NOT NULL))),
    CONSTRAINT alerts_check1 CHECK (((status <> 'reviewed'::text) OR (reviewed_at IS NOT NULL))),
    CONSTRAINT alerts_check2 CHECK (((status <> 'resolved'::text) OR (resolved_at IS NOT NULL))),
    CONSTRAINT alerts_status_check CHECK ((status = ANY (ARRAY['open'::text, 'acknowledged'::text, 'reviewed'::text, 'resolved'::text]))),
    CONSTRAINT alerts_trigger_source_check CHECK ((trigger_source = ANY (ARRAY['rule_engine'::text, 'clinician'::text, 'patient'::text])))
);


--
-- Name: audit_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_log (
    id bigint NOT NULL,
    table_name text NOT NULL,
    row_id uuid,
    action text NOT NULL,
    actor uuid,
    changed_at timestamp with time zone DEFAULT now() NOT NULL,
    old_data jsonb,
    new_data jsonb
);


--
-- Name: audit_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.audit_log ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.audit_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: body_measurements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.body_measurements (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    patient_id uuid NOT NULL,
    measured_at timestamp with time zone NOT NULL,
    weight_kg numeric(5,1),
    height_cm numeric(4,1),
    waist_cm numeric(4,1),
    source text NOT NULL,
    created_by uuid DEFAULT auth.uid(),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT body_measurements_check CHECK ((COALESCE(weight_kg, height_cm, waist_cm) IS NOT NULL)),
    CONSTRAINT body_measurements_height_cm_check CHECK (((height_cm >= (100)::numeric) AND (height_cm <= (230)::numeric))),
    CONSTRAINT body_measurements_source_check CHECK ((source = ANY (ARRAY['patient_reported'::text, 'clinician'::text, 'device'::text, 'simulated'::text]))),
    CONSTRAINT body_measurements_waist_cm_check CHECK (((waist_cm >= (40)::numeric) AND (waist_cm <= (200)::numeric))),
    CONSTRAINT body_measurements_weight_kg_check CHECK (((weight_kg >= (20)::numeric) AND (weight_kg <= (300)::numeric)))
);


--
-- Name: care_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.care_plans (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    patient_id uuid NOT NULL,
    clinician_id uuid NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    effective_from date NOT NULL,
    effective_to date,
    review_date date,
    target_systolic smallint,
    target_diastolic smallint,
    monitoring_readings_per_day smallint,
    monitoring_instructions text,
    lifestyle_recommendations text,
    follow_up_instructions text,
    clinician_guidance text NOT NULL,
    supersedes_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT care_plans_check CHECK (((effective_to IS NULL) OR (effective_to >= effective_from))),
    CONSTRAINT care_plans_check1 CHECK (((review_date IS NULL) OR (review_date >= effective_from))),
    CONSTRAINT care_plans_check2 CHECK (((target_systolic IS NULL) OR (target_diastolic IS NULL) OR (target_systolic > target_diastolic))),
    CONSTRAINT care_plans_monitoring_readings_per_day_check CHECK (((monitoring_readings_per_day >= 1) AND (monitoring_readings_per_day <= 12))),
    CONSTRAINT care_plans_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'active'::text, 'superseded'::text, 'completed'::text]))),
    CONSTRAINT care_plans_target_diastolic_check CHECK (((target_diastolic >= 50) AND (target_diastolic <= 130))),
    CONSTRAINT care_plans_target_systolic_check CHECK (((target_systolic >= 90) AND (target_systolic <= 200)))
);


--
-- Name: devices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.devices (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    patient_id uuid NOT NULL,
    device_type text NOT NULL,
    bp_capability text NOT NULL,
    manufacturer text,
    model text,
    external_device_id text,
    label text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT devices_bp_capability_check CHECK ((bp_capability = ANY (ARRAY['measured'::text, 'estimated'::text, 'none'::text, 'simulated'::text]))),
    CONSTRAINT devices_check CHECK (((device_type = 'simulator'::text) = (bp_capability = 'simulated'::text))),
    CONSTRAINT devices_device_type_check CHECK ((device_type = ANY (ARRAY['bp_cuff'::text, 'wearable'::text, 'phone_app'::text, 'simulator'::text])))
);


--
-- Name: doctor_notes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.doctor_notes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    doctor_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    note text NOT NULL,
    advice text,
    follow_up_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT doctor_notes_note_check CHECK (((length(note) >= 1) AND (length(note) <= 8000)))
);


--
-- Name: doctor_patient_assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.doctor_patient_assignments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    doctor_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    ended_at timestamp with time zone,
    CONSTRAINT doctor_patient_assignments_check CHECK ((doctor_id <> patient_id)),
    CONSTRAINT doctor_patient_assignments_check1 CHECK (((status = 'ended'::text) = (ended_at IS NOT NULL))),
    CONSTRAINT doctor_patient_assignments_status_check CHECK ((status = ANY (ARRAY['active'::text, 'ended'::text])))
);


--
-- Name: emergency_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.emergency_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    patient_id uuid NOT NULL,
    alert_id uuid,
    trigger_reason text NOT NULL,
    symptoms_snapshot text[] DEFAULT '{}'::text[] NOT NULL,
    location_lat double precision,
    location_lon double precision,
    location_shared_with_consent boolean DEFAULT false NOT NULL,
    actions_attempted jsonb DEFAULT '[]'::jsonb NOT NULL,
    reported_outcome text,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    ended_at timestamp with time zone,
    CONSTRAINT emergency_events_check CHECK (((location_lat IS NULL) = (location_lon IS NULL))),
    CONSTRAINT emergency_events_check1 CHECK (((location_lat IS NULL) OR location_shared_with_consent)),
    CONSTRAINT emergency_events_check2 CHECK (((ended_at IS NULL) OR (ended_at >= started_at))),
    CONSTRAINT emergency_events_location_lat_check CHECK (((location_lat >= ('-90'::integer)::double precision) AND (location_lat <= (90)::double precision))),
    CONSTRAINT emergency_events_location_lon_check CHECK (((location_lon >= ('-180'::integer)::double precision) AND (location_lon <= (180)::double precision)))
);


--
-- Name: ingestion_batches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ingestion_batches (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    patient_id uuid NOT NULL,
    source text NOT NULL,
    device_id uuid,
    file_name text,
    file_sha256 text,
    rows_total integer DEFAULT 0 NOT NULL,
    rows_inserted integer DEFAULT 0 NOT NULL,
    rows_duplicate integer DEFAULT 0 NOT NULL,
    rows_rejected integer DEFAULT 0 NOT NULL,
    rejections jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ingestion_batches_file_sha256_check CHECK ((file_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ingestion_batches_rows_duplicate_check CHECK ((rows_duplicate >= 0)),
    CONSTRAINT ingestion_batches_rows_inserted_check CHECK ((rows_inserted >= 0)),
    CONSTRAINT ingestion_batches_rows_rejected_check CHECK ((rows_rejected >= 0)),
    CONSTRAINT ingestion_batches_rows_total_check CHECK ((rows_total >= 0)),
    CONSTRAINT ingestion_batches_source_check CHECK ((source = ANY (ARRAY['csv_import'::text, 'device_sync'::text, 'simulated'::text])))
);


--
-- Name: journal_entries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.journal_entries (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    patient_id uuid NOT NULL,
    category text NOT NULL,
    entry_text text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    doctor_review_status text DEFAULT 'not_reviewed'::text NOT NULL,
    reviewed_by uuid,
    reviewed_at timestamp with time zone,
    CONSTRAINT journal_entries_category_check CHECK ((category = ANY (ARRAY['symptoms'::text, 'food'::text, 'activity'::text, 'medication'::text, 'question'::text, 'other'::text]))),
    CONSTRAINT journal_entries_check CHECK (((doctor_review_status = 'reviewed'::text) = (reviewed_at IS NOT NULL))),
    CONSTRAINT journal_entries_doctor_review_status_check CHECK ((doctor_review_status = ANY (ARRAY['not_reviewed'::text, 'reviewed'::text]))),
    CONSTRAINT journal_entries_entry_text_check CHECK (((length(entry_text) >= 1) AND (length(entry_text) <= 4000)))
);


--
-- Name: lifestyle_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.lifestyle_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    patient_id uuid NOT NULL,
    category text NOT NULL,
    started_at timestamp with time zone NOT NULL,
    ended_at timestamp with time zone,
    source text DEFAULT 'patient_reported'::text NOT NULL,
    description text,
    meal_type text,
    sodium_mg numeric(7,1),
    sodium_basis text,
    activity_type text,
    intensity text,
    steps integer,
    sleep_quality smallint,
    stress_level smallint,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT lifestyle_activity_fields CHECK (((category = 'activity'::text) OR ((activity_type IS NULL) AND (intensity IS NULL) AND (steps IS NULL)))),
    CONSTRAINT lifestyle_logs_activity_type_check CHECK ((length(activity_type) <= 100)),
    CONSTRAINT lifestyle_logs_category_check CHECK ((category = ANY (ARRAY['meal'::text, 'activity'::text, 'sleep'::text, 'stress'::text, 'fasting'::text, 'other'::text]))),
    CONSTRAINT lifestyle_logs_description_check CHECK ((length(description) <= 1000)),
    CONSTRAINT lifestyle_logs_intensity_check CHECK ((intensity = ANY (ARRAY['light'::text, 'moderate'::text, 'vigorous'::text]))),
    CONSTRAINT lifestyle_logs_meal_type_check CHECK ((meal_type = ANY (ARRAY['breakfast'::text, 'lunch'::text, 'dinner'::text, 'snack'::text]))),
    CONSTRAINT lifestyle_logs_sleep_quality_check CHECK (((sleep_quality >= 1) AND (sleep_quality <= 5))),
    CONSTRAINT lifestyle_logs_sodium_basis_check CHECK ((sodium_basis = ANY (ARRAY['label'::text, 'estimated'::text]))),
    CONSTRAINT lifestyle_logs_sodium_mg_check CHECK ((sodium_mg >= (0)::numeric)),
    CONSTRAINT lifestyle_logs_source_check CHECK ((source = ANY (ARRAY['patient_reported'::text, 'device'::text, 'simulated'::text]))),
    CONSTRAINT lifestyle_logs_steps_check CHECK ((steps >= 0)),
    CONSTRAINT lifestyle_logs_stress_level_check CHECK (((stress_level >= 1) AND (stress_level <= 5))),
    CONSTRAINT lifestyle_meal_fields CHECK (((category = 'meal'::text) OR ((meal_type IS NULL) AND (sodium_mg IS NULL)))),
    CONSTRAINT lifestyle_sleep_end CHECK (((category <> 'sleep'::text) OR (ended_at IS NOT NULL))),
    CONSTRAINT lifestyle_sleep_fields CHECK (((category = 'sleep'::text) OR (sleep_quality IS NULL))),
    CONSTRAINT lifestyle_sodium_basis CHECK (((sodium_mg IS NULL) = (sodium_basis IS NULL))),
    CONSTRAINT lifestyle_stress_fields CHECK (((category = 'stress'::text) OR (stress_level IS NULL))),
    CONSTRAINT lifestyle_time_order CHECK (((ended_at IS NULL) OR ((ended_at >= started_at) AND (ended_at <= (started_at + '24:00:00'::interval)))))
);


--
-- Name: measurements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.measurements (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    patient_id uuid NOT NULL,
    device_id uuid,
    ingestion_batch_id uuid,
    source text NOT NULL,
    provenance text DEFAULT 'measured'::text NOT NULL,
    method text DEFAULT 'unknown'::text NOT NULL,
    systolic smallint NOT NULL,
    diastolic smallint NOT NULL,
    pulse smallint,
    unit text DEFAULT 'mmHg'::text NOT NULL,
    measured_at timestamp with time zone NOT NULL,
    measured_tz text,
    body_position text,
    arm text,
    context text,
    external_id text,
    validation_status text DEFAULT 'needs_review'::text NOT NULL,
    quality_flags text[] DEFAULT '{}'::text[] NOT NULL,
    validation_policy_version text DEFAULT 'unvalidated'::text NOT NULL,
    raw_payload jsonb,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    rested_5_min boolean,
    CONSTRAINT measurements_arm_check CHECK ((arm = ANY (ARRAY['left'::text, 'right'::text]))),
    CONSTRAINT measurements_body_position_check CHECK ((body_position = ANY (ARRAY['sitting'::text, 'standing'::text, 'lying'::text]))),
    CONSTRAINT measurements_context_check CHECK ((length(context) <= 500)),
    CONSTRAINT measurements_diastolic_check CHECK (((diastolic >= 1) AND (diastolic <= 300))),
    CONSTRAINT measurements_estimate_labelled CHECK (((method <> 'wearable_estimate'::text) OR (provenance = 'estimated'::text))),
    CONSTRAINT measurements_external_needs_device CHECK (((external_id IS NULL) OR (device_id IS NOT NULL))),
    CONSTRAINT measurements_measured_tz_check CHECK (((measured_tz IS NULL) OR private.is_valid_tz(measured_tz))),
    CONSTRAINT measurements_method_check CHECK ((method = ANY (ARRAY['cuff_oscillometric'::text, 'cuff_auscultatory'::text, 'wearable_estimate'::text, 'unknown'::text]))),
    CONSTRAINT measurements_provenance_check CHECK ((provenance = ANY (ARRAY['measured'::text, 'estimated'::text, 'simulated'::text]))),
    CONSTRAINT measurements_pulse_check CHECK (((pulse >= 1) AND (pulse <= 400))),
    CONSTRAINT measurements_quality_flags_check CHECK ((quality_flags <@ ARRAY['systolic_not_above_diastolic'::text, 'systolic_implausible'::text, 'diastolic_implausible'::text, 'pulse_implausible'::text, 'measured_in_future'::text, 'unusual_value_recheck'::text, 'estimated_not_cuff'::text, 'possible_duplicate'::text, 'body_movement'::text, 'cuff_fit_issue'::text, 'irregular_pulse'::text, 'improper_position'::text])),
    CONSTRAINT measurements_raw_payload_check CHECK ((pg_column_size(raw_payload) <= 16384)),
    CONSTRAINT measurements_simulated_labelled CHECK (((source <> 'simulated'::text) OR (provenance = 'simulated'::text))),
    CONSTRAINT measurements_source_check CHECK ((source = ANY (ARRAY['manual'::text, 'device_sync'::text, 'csv_import'::text, 'simulated'::text]))),
    CONSTRAINT measurements_systolic_check CHECK (((systolic >= 1) AND (systolic <= 400))),
    CONSTRAINT measurements_unit_check CHECK ((unit = 'mmHg'::text)),
    CONSTRAINT measurements_valid_order CHECK (((validation_status <> 'valid'::text) OR (systolic > diastolic))),
    CONSTRAINT measurements_validation_status_check CHECK ((validation_status = ANY (ARRAY['valid'::text, 'needs_review'::text, 'invalid'::text])))
);


--
-- Name: medication_adherence_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.medication_adherence_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    patient_id uuid NOT NULL,
    medication_id uuid NOT NULL,
    status text NOT NULL,
    scheduled_for timestamp with time zone,
    taken_at timestamp with time zone,
    source text DEFAULT 'patient_reported'::text NOT NULL,
    note text,
    reported_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT medication_adherence_events_check CHECK (((status = 'taken'::text) OR (taken_at IS NULL))),
    CONSTRAINT medication_adherence_events_note_check CHECK ((length(note) <= 500)),
    CONSTRAINT medication_adherence_events_source_check CHECK ((source = ANY (ARRAY['patient_reported'::text, 'device'::text, 'simulated'::text]))),
    CONSTRAINT medication_adherence_events_status_check CHECK ((status = ANY (ARRAY['taken'::text, 'missed'::text, 'skipped'::text])))
);


--
-- Name: medications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.medications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    patient_id uuid NOT NULL,
    name text NOT NULL,
    dose_text text,
    schedule_text text,
    source text NOT NULL,
    prescribed_by uuid,
    active boolean DEFAULT true NOT NULL,
    started_on date,
    ended_on date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT medications_check CHECK (((ended_on IS NULL) OR (started_on IS NULL) OR (ended_on >= started_on))),
    CONSTRAINT medications_check1 CHECK (((source = 'clinician'::text) = (prescribed_by IS NOT NULL))),
    CONSTRAINT medications_name_check CHECK ((length(name) <= 200)),
    CONSTRAINT medications_source_check CHECK ((source = ANY (ARRAY['clinician'::text, 'patient_reported'::text])))
);


--
-- Name: ml_predictions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ml_predictions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    patient_id uuid NOT NULL,
    target_date date NOT NULL,
    target text NOT NULL,
    status text NOT NULL,
    predicted_systolic numeric(5,1),
    predicted_diastolic numeric(5,1),
    interval_systolic_low numeric(5,1),
    interval_systolic_high numeric(5,1),
    interval_diastolic_low numeric(5,1),
    interval_diastolic_high numeric(5,1),
    model_version text NOT NULL,
    trained_on text NOT NULL,
    features_until timestamp with time zone NOT NULL,
    n_readings_used integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ml_predictions_interval_order CHECK ((((interval_systolic_low IS NULL) OR (interval_systolic_low <= interval_systolic_high)) AND ((interval_diastolic_low IS NULL) OR (interval_diastolic_low <= interval_diastolic_high)))),
    CONSTRAINT ml_predictions_n_readings_used_check CHECK ((n_readings_used >= 0)),
    CONSTRAINT ml_predictions_status_check CHECK ((status = ANY (ARRAY['ok'::text, 'insufficient_history'::text]))),
    CONSTRAINT ml_predictions_target_check CHECK ((target = 'morning_mean_bp'::text)),
    CONSTRAINT ml_predictions_values_iff_ok CHECK (((status = 'ok'::text) = ((predicted_systolic IS NOT NULL) AND (predicted_diastolic IS NOT NULL))))
);


--
-- Name: patient_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_profiles (
    user_id uuid NOT NULL,
    relevant_conditions text[] DEFAULT '{}'::text[] NOT NULL,
    allergies text,
    medication_context text,
    regular_doctor_id uuid,
    regular_clinic text,
    emergency_preferences jsonb DEFAULT '{}'::jsonb NOT NULL,
    consent_location boolean DEFAULT false NOT NULL,
    data_consent_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    birth_year smallint,
    sex text,
    smoking_status text,
    condition_codes text[] DEFAULT '{}'::text[] NOT NULL,
    bread_portions_per_day smallint,
    adds_salt_at_table text,
    salty_processed_food text,
    CONSTRAINT patient_profiles_adds_salt_at_table_check CHECK ((adds_salt_at_table = ANY (ARRAY['never'::text, 'rarely'::text, 'sometimes'::text, 'often'::text, 'always'::text]))),
    CONSTRAINT patient_profiles_birth_year_check CHECK (((birth_year >= 1900) AND (birth_year <= 2100))),
    CONSTRAINT patient_profiles_bread_portions_per_day_check CHECK (((bread_portions_per_day >= 0) AND (bread_portions_per_day <= 20))),
    CONSTRAINT patient_profiles_condition_codes_check CHECK ((condition_codes <@ ARRAY['hypertension'::text, 'diabetes'::text, 'dyslipidemia'::text, 'chronic_kidney_disease'::text, 'heart_disease'::text, 'stroke_history'::text, 'pregnancy'::text])),
    CONSTRAINT patient_profiles_salty_processed_food_check CHECK ((salty_processed_food = ANY (ARRAY['never'::text, 'rarely'::text, 'sometimes'::text, 'often'::text, 'always'::text]))),
    CONSTRAINT patient_profiles_sex_check CHECK ((sex = ANY (ARRAY['female'::text, 'male'::text]))),
    CONSTRAINT patient_profiles_smoking_status_check CHECK ((smoking_status = ANY (ARRAY['never'::text, 'former'::text, 'current'::text])))
);


--
-- Name: profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.profiles (
    id uuid NOT NULL,
    role text DEFAULT 'patient'::text NOT NULL,
    display_name text NOT NULL,
    timezone text DEFAULT 'Africa/Algiers'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    preferred_language text,
    CONSTRAINT profiles_display_name_check CHECK (((length(TRIM(BOTH FROM display_name)) >= 1) AND (length(TRIM(BOTH FROM display_name)) <= 120))),
    CONSTRAINT profiles_preferred_language_check CHECK ((preferred_language = ANY (ARRAY['fr'::text, 'ar'::text]))),
    CONSTRAINT profiles_role_check CHECK ((role = ANY (ARRAY['patient'::text, 'doctor'::text, 'admin'::text]))),
    CONSTRAINT profiles_timezone_check CHECK (private.is_valid_tz(timezone))
);


--
-- Name: symptom_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.symptom_reports (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    patient_id uuid NOT NULL,
    symptoms text[] NOT NULL,
    onset_at timestamp with time zone,
    reported_at timestamp with time zone DEFAULT now() NOT NULL,
    source text DEFAULT 'patient_reported'::text NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT symptom_reports_check CHECK (((onset_at IS NULL) OR (onset_at <= (reported_at + '00:05:00'::interval)))),
    CONSTRAINT symptom_reports_notes_check CHECK ((length(notes) <= 2000)),
    CONSTRAINT symptom_reports_source_check CHECK ((source = ANY (ARRAY['patient_reported'::text, 'bystander'::text, 'clinician'::text, 'simulated'::text]))),
    CONSTRAINT symptom_reports_symptoms_check CHECK ((symptoms <@ ARRAY['chest_pain'::text, 'shortness_of_breath'::text, 'back_pain'::text, 'weakness'::text, 'numbness'::text, 'vision_change'::text, 'difficulty_speaking'::text, 'severe_headache'::text, 'confusion'::text, 'dizziness'::text, 'nausea'::text, 'palpitations'::text, 'other'::text]))
);


--
-- Name: trusted_contacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trusted_contacts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    patient_id uuid NOT NULL,
    name text NOT NULL,
    relationship text,
    phone text NOT NULL,
    consented_at timestamp with time zone DEFAULT now() NOT NULL,
    active boolean DEFAULT true NOT NULL,
    CONSTRAINT trusted_contacts_phone_check CHECK ((phone ~ '^\+?[0-9 ()-]{6,20}$'::text))
);


--
-- Name: wearable_samples; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wearable_samples (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    patient_id uuid NOT NULL,
    device_id uuid NOT NULL,
    metric text NOT NULL,
    value numeric(6,2) NOT NULL,
    unit text NOT NULL,
    measured_at timestamp with time zone NOT NULL,
    source text NOT NULL,
    external_id text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT wearable_metric_unit CHECK ((((((metric = 'heart_rate'::text) AND (unit = 'bpm'::text)) OR ((metric = 'hrv_rmssd'::text) AND (unit = 'ms'::text))) OR ((metric = 'spo2'::text) AND (unit = 'percent'::text))) OR ((metric = 'skin_temperature'::text) AND (unit = 'celsius'::text)))),
    CONSTRAINT wearable_samples_source_check CHECK ((source = ANY (ARRAY['device_sync'::text, 'csv_import'::text, 'simulated'::text]))),
    CONSTRAINT wearable_value_range CHECK (
CASE metric
    WHEN 'heart_rate'::text THEN ((value >= (25)::numeric) AND (value <= (250)::numeric))
    WHEN 'hrv_rmssd'::text THEN ((value >= (1)::numeric) AND (value <= (300)::numeric))
    WHEN 'spo2'::text THEN ((value >= (50)::numeric) AND (value <= (100)::numeric))
    WHEN 'skin_temperature'::text THEN ((value >= (20)::numeric) AND (value <= (45)::numeric))
    ELSE NULL::boolean
END)
);


--
-- Name: alert_measurements alert_measurements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_measurements
    ADD CONSTRAINT alert_measurements_pkey PRIMARY KEY (alert_id, measurement_id);


--
-- Name: alerts alerts_id_patient_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_id_patient_id_key UNIQUE (id, patient_id);


--
-- Name: alerts alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_pkey PRIMARY KEY (id);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (id);


--
-- Name: body_measurements body_measurements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.body_measurements
    ADD CONSTRAINT body_measurements_pkey PRIMARY KEY (id);


--
-- Name: care_plans care_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_plans
    ADD CONSTRAINT care_plans_pkey PRIMARY KEY (id);


--
-- Name: devices devices_id_patient_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.devices
    ADD CONSTRAINT devices_id_patient_id_key UNIQUE (id, patient_id);


--
-- Name: devices devices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.devices
    ADD CONSTRAINT devices_pkey PRIMARY KEY (id);


--
-- Name: doctor_notes doctor_notes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doctor_notes
    ADD CONSTRAINT doctor_notes_pkey PRIMARY KEY (id);


--
-- Name: doctor_patient_assignments doctor_patient_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doctor_patient_assignments
    ADD CONSTRAINT doctor_patient_assignments_pkey PRIMARY KEY (id);


--
-- Name: emergency_events emergency_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emergency_events
    ADD CONSTRAINT emergency_events_pkey PRIMARY KEY (id);


--
-- Name: ingestion_batches ingestion_batches_id_patient_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_batches
    ADD CONSTRAINT ingestion_batches_id_patient_id_key UNIQUE (id, patient_id);


--
-- Name: ingestion_batches ingestion_batches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_batches
    ADD CONSTRAINT ingestion_batches_pkey PRIMARY KEY (id);


--
-- Name: journal_entries journal_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.journal_entries
    ADD CONSTRAINT journal_entries_pkey PRIMARY KEY (id);


--
-- Name: lifestyle_logs lifestyle_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lifestyle_logs
    ADD CONSTRAINT lifestyle_logs_pkey PRIMARY KEY (id);


--
-- Name: measurements measurements_id_patient_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.measurements
    ADD CONSTRAINT measurements_id_patient_id_key UNIQUE (id, patient_id);


--
-- Name: measurements measurements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.measurements
    ADD CONSTRAINT measurements_pkey PRIMARY KEY (id);


--
-- Name: medication_adherence_events medication_adherence_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medication_adherence_events
    ADD CONSTRAINT medication_adherence_events_pkey PRIMARY KEY (id);


--
-- Name: medications medications_id_patient_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medications
    ADD CONSTRAINT medications_id_patient_id_key UNIQUE (id, patient_id);


--
-- Name: medications medications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medications
    ADD CONSTRAINT medications_pkey PRIMARY KEY (id);


--
-- Name: ml_predictions ml_predictions_patient_id_target_date_model_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ml_predictions
    ADD CONSTRAINT ml_predictions_patient_id_target_date_model_version_key UNIQUE (patient_id, target_date, model_version);


--
-- Name: ml_predictions ml_predictions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ml_predictions
    ADD CONSTRAINT ml_predictions_pkey PRIMARY KEY (id);


--
-- Name: patient_profiles patient_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_profiles
    ADD CONSTRAINT patient_profiles_pkey PRIMARY KEY (user_id);


--
-- Name: profiles profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profiles
    ADD CONSTRAINT profiles_pkey PRIMARY KEY (id);


--
-- Name: symptom_reports symptom_reports_id_patient_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.symptom_reports
    ADD CONSTRAINT symptom_reports_id_patient_id_key UNIQUE (id, patient_id);


--
-- Name: symptom_reports symptom_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.symptom_reports
    ADD CONSTRAINT symptom_reports_pkey PRIMARY KEY (id);


--
-- Name: trusted_contacts trusted_contacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trusted_contacts
    ADD CONSTRAINT trusted_contacts_pkey PRIMARY KEY (id);


--
-- Name: wearable_samples wearable_samples_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wearable_samples
    ADD CONSTRAINT wearable_samples_pkey PRIMARY KEY (id);


--
-- Name: adherence_patient_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX adherence_patient_time ON public.medication_adherence_events USING btree (patient_id, reported_at DESC);


--
-- Name: alert_measurements_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX alert_measurements_patient ON public.alert_measurements USING btree (patient_id);


--
-- Name: alerts_once_per_measurement; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX alerts_once_per_measurement ON public.alerts USING btree (measurement_id, rule_code) WHERE (measurement_id IS NOT NULL);


--
-- Name: alerts_once_per_symptom_report; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX alerts_once_per_symptom_report ON public.alerts USING btree (symptom_report_id, rule_code) WHERE (symptom_report_id IS NOT NULL);


--
-- Name: alerts_patient_status_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX alerts_patient_status_time ON public.alerts USING btree (patient_id, status, created_at DESC);


--
-- Name: assignments_one_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX assignments_one_active ON public.doctor_patient_assignments USING btree (doctor_id, patient_id) WHERE (status = 'active'::text);


--
-- Name: assignments_patient; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX assignments_patient ON public.doctor_patient_assignments USING btree (patient_id) WHERE (status = 'active'::text);


--
-- Name: audit_row; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX audit_row ON public.audit_log USING btree (table_name, row_id);


--
-- Name: batches_file_once; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX batches_file_once ON public.ingestion_batches USING btree (patient_id, file_sha256) WHERE (file_sha256 IS NOT NULL);


--
-- Name: body_measurements_patient_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX body_measurements_patient_time ON public.body_measurements USING btree (patient_id, measured_at DESC);


--
-- Name: care_plans_one_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX care_plans_one_active ON public.care_plans USING btree (patient_id) WHERE (status = 'active'::text);


--
-- Name: devices_external_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX devices_external_id ON public.devices USING btree (patient_id, external_device_id) WHERE (external_device_id IS NOT NULL);


--
-- Name: doctor_notes_patient_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX doctor_notes_patient_time ON public.doctor_notes USING btree (patient_id, created_at DESC);


--
-- Name: emergency_patient_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX emergency_patient_time ON public.emergency_events USING btree (patient_id, started_at DESC);


--
-- Name: journal_patient_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX journal_patient_time ON public.journal_entries USING btree (patient_id, created_at DESC);


--
-- Name: lifestyle_patient_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX lifestyle_patient_time ON public.lifestyle_logs USING btree (patient_id, started_at DESC);


--
-- Name: measurements_device_reading; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX measurements_device_reading ON public.measurements USING btree (device_id, external_id) WHERE (external_id IS NOT NULL);


--
-- Name: measurements_patient_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX measurements_patient_time ON public.measurements USING btree (patient_id, measured_at DESC);


--
-- Name: ml_predictions_patient_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ml_predictions_patient_date ON public.ml_predictions USING btree (patient_id, target_date DESC);


--
-- Name: symptoms_patient_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX symptoms_patient_time ON public.symptom_reports USING btree (patient_id, reported_at DESC);


--
-- Name: wearable_samples_device_sample; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX wearable_samples_device_sample ON public.wearable_samples USING btree (device_id, external_id) WHERE (external_id IS NOT NULL);


--
-- Name: wearable_samples_patient_metric_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX wearable_samples_patient_metric_time ON public.wearable_samples USING btree (patient_id, metric, measured_at DESC);


--
-- Name: alerts alerts_audit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER alerts_audit AFTER INSERT OR DELETE OR UPDATE ON public.alerts FOR EACH ROW EXECUTE FUNCTION private.audit();


--
-- Name: doctor_patient_assignments assignments_roles; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER assignments_roles BEFORE INSERT OR UPDATE ON public.doctor_patient_assignments FOR EACH ROW EXECUTE FUNCTION private.enforce_roles('doctor_id', 'doctor', 'patient_id', 'patient');


--
-- Name: care_plans care_plans_audit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER care_plans_audit AFTER INSERT OR DELETE OR UPDATE ON public.care_plans FOR EACH ROW EXECUTE FUNCTION private.audit();


--
-- Name: care_plans care_plans_roles; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER care_plans_roles BEFORE INSERT OR UPDATE ON public.care_plans FOR EACH ROW EXECUTE FUNCTION private.enforce_roles('clinician_id', 'doctor', 'patient_id', 'patient');


--
-- Name: care_plans care_plans_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER care_plans_touch BEFORE UPDATE ON public.care_plans FOR EACH ROW EXECUTE FUNCTION private.touch_updated_at();


--
-- Name: doctor_notes doctor_notes_audit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER doctor_notes_audit AFTER INSERT OR DELETE OR UPDATE ON public.doctor_notes FOR EACH ROW EXECUTE FUNCTION private.audit();


--
-- Name: doctor_notes doctor_notes_roles; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER doctor_notes_roles BEFORE INSERT OR UPDATE ON public.doctor_notes FOR EACH ROW EXECUTE FUNCTION private.enforce_roles('doctor_id', 'doctor', 'patient_id', 'patient');


--
-- Name: doctor_notes doctor_notes_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER doctor_notes_touch BEFORE UPDATE ON public.doctor_notes FOR EACH ROW EXECUTE FUNCTION private.touch_updated_at();


--
-- Name: doctor_patient_assignments doctor_patient_assignments_audit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER doctor_patient_assignments_audit AFTER INSERT OR DELETE OR UPDATE ON public.doctor_patient_assignments FOR EACH ROW EXECUTE FUNCTION private.audit();


--
-- Name: doctor_patient_assignments doctor_patient_assignments_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER doctor_patient_assignments_touch BEFORE UPDATE ON public.doctor_patient_assignments FOR EACH ROW EXECUTE FUNCTION private.touch_updated_at();


--
-- Name: lifestyle_logs lifestyle_logs_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER lifestyle_logs_touch BEFORE UPDATE ON public.lifestyle_logs FOR EACH ROW EXECUTE FUNCTION private.touch_updated_at();


--
-- Name: measurements measurements_validate; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER measurements_validate BEFORE INSERT OR UPDATE OF systolic, diastolic, pulse, measured_at, provenance, quality_flags ON public.measurements FOR EACH ROW EXECUTE FUNCTION private.validate_measurement();


--
-- Name: medications medications_audit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER medications_audit AFTER INSERT OR DELETE OR UPDATE ON public.medications FOR EACH ROW EXECUTE FUNCTION private.audit();


--
-- Name: medications medications_roles; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER medications_roles BEFORE INSERT OR UPDATE ON public.medications FOR EACH ROW EXECUTE FUNCTION private.enforce_roles('prescribed_by', 'doctor', 'patient_id', 'patient');


--
-- Name: medications medications_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER medications_touch BEFORE UPDATE ON public.medications FOR EACH ROW EXECUTE FUNCTION private.touch_updated_at();


--
-- Name: patient_profiles patient_profiles_roles; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER patient_profiles_roles BEFORE INSERT OR UPDATE ON public.patient_profiles FOR EACH ROW EXECUTE FUNCTION private.enforce_roles('user_id', 'patient', 'regular_doctor_id', 'doctor');


--
-- Name: patient_profiles patient_profiles_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER patient_profiles_touch BEFORE UPDATE ON public.patient_profiles FOR EACH ROW EXECUTE FUNCTION private.touch_updated_at();


--
-- Name: profiles profiles_audit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER profiles_audit AFTER INSERT OR DELETE OR UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION private.audit();


--
-- Name: profiles profiles_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER profiles_touch BEFORE UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION private.touch_updated_at();


--
-- Name: alert_measurements alert_measurements_alert_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_measurements
    ADD CONSTRAINT alert_measurements_alert_id_patient_id_fkey FOREIGN KEY (alert_id, patient_id) REFERENCES public.alerts(id, patient_id) ON DELETE CASCADE;


--
-- Name: alert_measurements alert_measurements_measurement_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_measurements
    ADD CONSTRAINT alert_measurements_measurement_id_patient_id_fkey FOREIGN KEY (measurement_id, patient_id) REFERENCES public.measurements(id, patient_id);


--
-- Name: alerts alerts_acknowledged_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_acknowledged_by_fkey FOREIGN KEY (acknowledged_by) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: alerts alerts_measurement_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_measurement_id_patient_id_fkey FOREIGN KEY (measurement_id, patient_id) REFERENCES public.measurements(id, patient_id);


--
-- Name: alerts alerts_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: alerts alerts_resolved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_resolved_by_fkey FOREIGN KEY (resolved_by) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: alerts alerts_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: alerts alerts_symptom_report_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_symptom_report_id_patient_id_fkey FOREIGN KEY (symptom_report_id, patient_id) REFERENCES public.symptom_reports(id, patient_id);


--
-- Name: body_measurements body_measurements_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.body_measurements
    ADD CONSTRAINT body_measurements_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: body_measurements body_measurements_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.body_measurements
    ADD CONSTRAINT body_measurements_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: care_plans care_plans_clinician_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_plans
    ADD CONSTRAINT care_plans_clinician_id_fkey FOREIGN KEY (clinician_id) REFERENCES public.profiles(id) ON DELETE RESTRICT;


--
-- Name: care_plans care_plans_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_plans
    ADD CONSTRAINT care_plans_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: care_plans care_plans_supersedes_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_plans
    ADD CONSTRAINT care_plans_supersedes_id_fkey FOREIGN KEY (supersedes_id) REFERENCES public.care_plans(id) ON DELETE SET NULL;


--
-- Name: devices devices_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.devices
    ADD CONSTRAINT devices_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: doctor_notes doctor_notes_doctor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doctor_notes
    ADD CONSTRAINT doctor_notes_doctor_id_fkey FOREIGN KEY (doctor_id) REFERENCES public.profiles(id) ON DELETE RESTRICT;


--
-- Name: doctor_notes doctor_notes_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doctor_notes
    ADD CONSTRAINT doctor_notes_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: doctor_patient_assignments doctor_patient_assignments_doctor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doctor_patient_assignments
    ADD CONSTRAINT doctor_patient_assignments_doctor_id_fkey FOREIGN KEY (doctor_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: doctor_patient_assignments doctor_patient_assignments_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doctor_patient_assignments
    ADD CONSTRAINT doctor_patient_assignments_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: emergency_events emergency_events_alert_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emergency_events
    ADD CONSTRAINT emergency_events_alert_id_fkey FOREIGN KEY (alert_id) REFERENCES public.alerts(id) ON DELETE SET NULL;


--
-- Name: emergency_events emergency_events_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emergency_events
    ADD CONSTRAINT emergency_events_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: ingestion_batches ingestion_batches_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_batches
    ADD CONSTRAINT ingestion_batches_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: ingestion_batches ingestion_batches_device_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_batches
    ADD CONSTRAINT ingestion_batches_device_id_patient_id_fkey FOREIGN KEY (device_id, patient_id) REFERENCES public.devices(id, patient_id);


--
-- Name: ingestion_batches ingestion_batches_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_batches
    ADD CONSTRAINT ingestion_batches_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: journal_entries journal_entries_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.journal_entries
    ADD CONSTRAINT journal_entries_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: journal_entries journal_entries_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.journal_entries
    ADD CONSTRAINT journal_entries_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: lifestyle_logs lifestyle_logs_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lifestyle_logs
    ADD CONSTRAINT lifestyle_logs_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: measurements measurements_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.measurements
    ADD CONSTRAINT measurements_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: measurements measurements_device_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.measurements
    ADD CONSTRAINT measurements_device_id_patient_id_fkey FOREIGN KEY (device_id, patient_id) REFERENCES public.devices(id, patient_id);


--
-- Name: measurements measurements_ingestion_batch_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.measurements
    ADD CONSTRAINT measurements_ingestion_batch_id_patient_id_fkey FOREIGN KEY (ingestion_batch_id, patient_id) REFERENCES public.ingestion_batches(id, patient_id);


--
-- Name: measurements measurements_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.measurements
    ADD CONSTRAINT measurements_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: medication_adherence_events medication_adherence_events_medication_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medication_adherence_events
    ADD CONSTRAINT medication_adherence_events_medication_id_patient_id_fkey FOREIGN KEY (medication_id, patient_id) REFERENCES public.medications(id, patient_id) ON DELETE CASCADE;


--
-- Name: medications medications_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medications
    ADD CONSTRAINT medications_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: medications medications_prescribed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medications
    ADD CONSTRAINT medications_prescribed_by_fkey FOREIGN KEY (prescribed_by) REFERENCES public.profiles(id) ON DELETE RESTRICT;


--
-- Name: ml_predictions ml_predictions_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ml_predictions
    ADD CONSTRAINT ml_predictions_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: patient_profiles patient_profiles_regular_doctor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_profiles
    ADD CONSTRAINT patient_profiles_regular_doctor_id_fkey FOREIGN KEY (regular_doctor_id) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: patient_profiles patient_profiles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_profiles
    ADD CONSTRAINT patient_profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: profiles profiles_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profiles
    ADD CONSTRAINT profiles_id_fkey FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: symptom_reports symptom_reports_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.symptom_reports
    ADD CONSTRAINT symptom_reports_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: trusted_contacts trusted_contacts_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trusted_contacts
    ADD CONSTRAINT trusted_contacts_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: wearable_samples wearable_samples_device_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wearable_samples
    ADD CONSTRAINT wearable_samples_device_id_patient_id_fkey FOREIGN KEY (device_id, patient_id) REFERENCES public.devices(id, patient_id);


--
-- Name: wearable_samples wearable_samples_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wearable_samples
    ADD CONSTRAINT wearable_samples_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: medication_adherence_events adherence_insert_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY adherence_insert_own ON public.medication_adherence_events FOR INSERT TO authenticated WITH CHECK (((patient_id = ( SELECT auth.uid() AS uid)) AND (source = 'patient_reported'::text)));


--
-- Name: alert_measurements; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.alert_measurements ENABLE ROW LEVEL SECURITY;

--
-- Name: alert_measurements alert_measurements_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY alert_measurements_read ON public.alert_measurements FOR SELECT TO authenticated USING (private.can_read_patient(patient_id));


--
-- Name: alerts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;

--
-- Name: alerts alerts_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY alerts_read ON public.alerts FOR SELECT TO authenticated USING (private.can_read_patient(patient_id));


--
-- Name: doctor_patient_assignments assignments_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY assignments_read ON public.doctor_patient_assignments FOR SELECT TO authenticated USING (((doctor_id = ( SELECT auth.uid() AS uid)) OR (patient_id = ( SELECT auth.uid() AS uid)) OR (private.current_app_role() = 'admin'::text)));


--
-- Name: audit_log; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

--
-- Name: audit_log audit_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY audit_read ON public.audit_log FOR SELECT TO authenticated USING ((private.current_app_role() = 'admin'::text));


--
-- Name: body_measurements; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.body_measurements ENABLE ROW LEVEL SECURITY;

--
-- Name: body_measurements body_measurements_insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY body_measurements_insert ON public.body_measurements FOR INSERT TO authenticated WITH CHECK ((((patient_id = ( SELECT auth.uid() AS uid)) AND (source = 'patient_reported'::text)) OR (private.is_assigned_doctor(patient_id) AND (source = 'clinician'::text))));


--
-- Name: body_measurements body_measurements_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY body_measurements_read ON public.body_measurements FOR SELECT TO authenticated USING (private.can_read_patient(patient_id));


--
-- Name: care_plans; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.care_plans ENABLE ROW LEVEL SECURITY;

--
-- Name: care_plans care_plans_insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY care_plans_insert ON public.care_plans FOR INSERT TO authenticated WITH CHECK (((clinician_id = ( SELECT auth.uid() AS uid)) AND private.is_assigned_doctor(patient_id)));


--
-- Name: care_plans care_plans_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY care_plans_read ON public.care_plans FOR SELECT TO authenticated USING (private.can_read_patient(patient_id));


--
-- Name: care_plans care_plans_update; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY care_plans_update ON public.care_plans FOR UPDATE TO authenticated USING (private.is_assigned_doctor(patient_id)) WITH CHECK (private.is_assigned_doctor(patient_id));


--
-- Name: trusted_contacts contacts_delete_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY contacts_delete_own ON public.trusted_contacts FOR DELETE TO authenticated USING ((patient_id = ( SELECT auth.uid() AS uid)));


--
-- Name: trusted_contacts contacts_insert_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY contacts_insert_own ON public.trusted_contacts FOR INSERT TO authenticated WITH CHECK ((patient_id = ( SELECT auth.uid() AS uid)));


--
-- Name: trusted_contacts contacts_update_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY contacts_update_own ON public.trusted_contacts FOR UPDATE TO authenticated USING ((patient_id = ( SELECT auth.uid() AS uid))) WITH CHECK ((patient_id = ( SELECT auth.uid() AS uid)));


--
-- Name: devices; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.devices ENABLE ROW LEVEL SECURITY;

--
-- Name: devices devices_insert_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY devices_insert_own ON public.devices FOR INSERT TO authenticated WITH CHECK (((patient_id = ( SELECT auth.uid() AS uid)) AND (device_type <> 'simulator'::text)));


--
-- Name: devices devices_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY devices_read ON public.devices FOR SELECT TO authenticated USING (private.can_read_patient(patient_id));


--
-- Name: devices devices_update_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY devices_update_own ON public.devices FOR UPDATE TO authenticated USING ((patient_id = ( SELECT auth.uid() AS uid))) WITH CHECK (((patient_id = ( SELECT auth.uid() AS uid)) AND (device_type <> 'simulator'::text)));


--
-- Name: doctor_notes; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.doctor_notes ENABLE ROW LEVEL SECURITY;

--
-- Name: doctor_notes doctor_notes_insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY doctor_notes_insert ON public.doctor_notes FOR INSERT TO authenticated WITH CHECK (((doctor_id = ( SELECT auth.uid() AS uid)) AND private.is_assigned_doctor(patient_id)));


--
-- Name: doctor_notes doctor_notes_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY doctor_notes_read ON public.doctor_notes FOR SELECT TO authenticated USING ((private.is_assigned_doctor(patient_id) OR (private.current_app_role() = 'admin'::text)));


--
-- Name: doctor_notes doctor_notes_update; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY doctor_notes_update ON public.doctor_notes FOR UPDATE TO authenticated USING (((doctor_id = ( SELECT auth.uid() AS uid)) AND private.is_assigned_doctor(patient_id))) WITH CHECK (((doctor_id = ( SELECT auth.uid() AS uid)) AND private.is_assigned_doctor(patient_id)));


--
-- Name: doctor_patient_assignments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.doctor_patient_assignments ENABLE ROW LEVEL SECURITY;

--
-- Name: emergency_events; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.emergency_events ENABLE ROW LEVEL SECURITY;

--
-- Name: emergency_events emergency_events_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY emergency_events_read ON public.emergency_events FOR SELECT TO authenticated USING (private.can_read_patient(patient_id));


--
-- Name: emergency_events emergency_insert_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY emergency_insert_own ON public.emergency_events FOR INSERT TO authenticated WITH CHECK ((patient_id = ( SELECT auth.uid() AS uid)));


--
-- Name: emergency_events emergency_update_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY emergency_update_own ON public.emergency_events FOR UPDATE TO authenticated USING ((patient_id = ( SELECT auth.uid() AS uid))) WITH CHECK ((patient_id = ( SELECT auth.uid() AS uid)));


--
-- Name: ingestion_batches; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.ingestion_batches ENABLE ROW LEVEL SECURITY;

--
-- Name: ingestion_batches ingestion_batches_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY ingestion_batches_read ON public.ingestion_batches FOR SELECT TO authenticated USING (private.can_read_patient(patient_id));


--
-- Name: journal_entries; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.journal_entries ENABLE ROW LEVEL SECURITY;

--
-- Name: journal_entries journal_entries_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY journal_entries_read ON public.journal_entries FOR SELECT TO authenticated USING (private.can_read_patient(patient_id));


--
-- Name: journal_entries journal_insert_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY journal_insert_own ON public.journal_entries FOR INSERT TO authenticated WITH CHECK (((patient_id = ( SELECT auth.uid() AS uid)) AND (doctor_review_status = 'not_reviewed'::text)));


--
-- Name: journal_entries journal_review_by_doctor; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY journal_review_by_doctor ON public.journal_entries FOR UPDATE TO authenticated USING (private.is_assigned_doctor(patient_id)) WITH CHECK ((private.is_assigned_doctor(patient_id) AND ((reviewed_by IS NULL) OR (reviewed_by = ( SELECT auth.uid() AS uid)))));


--
-- Name: lifestyle_logs lifestyle_delete_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY lifestyle_delete_own ON public.lifestyle_logs FOR DELETE TO authenticated USING ((patient_id = ( SELECT auth.uid() AS uid)));


--
-- Name: lifestyle_logs lifestyle_insert_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY lifestyle_insert_own ON public.lifestyle_logs FOR INSERT TO authenticated WITH CHECK (((patient_id = ( SELECT auth.uid() AS uid)) AND (source = 'patient_reported'::text)));


--
-- Name: lifestyle_logs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.lifestyle_logs ENABLE ROW LEVEL SECURITY;

--
-- Name: lifestyle_logs lifestyle_logs_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY lifestyle_logs_read ON public.lifestyle_logs FOR SELECT TO authenticated USING (private.can_read_patient(patient_id));


--
-- Name: lifestyle_logs lifestyle_update_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY lifestyle_update_own ON public.lifestyle_logs FOR UPDATE TO authenticated USING ((patient_id = ( SELECT auth.uid() AS uid))) WITH CHECK (((patient_id = ( SELECT auth.uid() AS uid)) AND (source = 'patient_reported'::text)));


--
-- Name: measurements; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.measurements ENABLE ROW LEVEL SECURITY;

--
-- Name: measurements measurements_insert_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY measurements_insert_own ON public.measurements FOR INSERT TO authenticated WITH CHECK (((patient_id = ( SELECT auth.uid() AS uid)) AND (source = 'manual'::text) AND (provenance <> 'simulated'::text) AND (ingestion_batch_id IS NULL)));


--
-- Name: measurements measurements_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY measurements_read ON public.measurements FOR SELECT TO authenticated USING (private.can_read_patient(patient_id));


--
-- Name: medication_adherence_events; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.medication_adherence_events ENABLE ROW LEVEL SECURITY;

--
-- Name: medication_adherence_events medication_adherence_events_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY medication_adherence_events_read ON public.medication_adherence_events FOR SELECT TO authenticated USING (private.can_read_patient(patient_id));


--
-- Name: medications; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.medications ENABLE ROW LEVEL SECURITY;

--
-- Name: medications medications_insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY medications_insert ON public.medications FOR INSERT TO authenticated WITH CHECK ((((patient_id = ( SELECT auth.uid() AS uid)) AND (source = 'patient_reported'::text) AND (prescribed_by IS NULL)) OR (private.is_assigned_doctor(patient_id) AND (source = 'clinician'::text) AND (prescribed_by = ( SELECT auth.uid() AS uid)))));


--
-- Name: medications medications_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY medications_read ON public.medications FOR SELECT TO authenticated USING (private.can_read_patient(patient_id));


--
-- Name: medications medications_update; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY medications_update ON public.medications FOR UPDATE TO authenticated USING ((((patient_id = ( SELECT auth.uid() AS uid)) AND (source = 'patient_reported'::text)) OR (private.is_assigned_doctor(patient_id) AND (source = 'clinician'::text)))) WITH CHECK ((((patient_id = ( SELECT auth.uid() AS uid)) AND (source = 'patient_reported'::text) AND (prescribed_by IS NULL)) OR (private.is_assigned_doctor(patient_id) AND (source = 'clinician'::text) AND (prescribed_by IS NOT NULL))));


--
-- Name: ml_predictions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.ml_predictions ENABLE ROW LEVEL SECURITY;

--
-- Name: ml_predictions ml_predictions_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY ml_predictions_read ON public.ml_predictions FOR SELECT TO authenticated USING ((private.is_assigned_doctor(patient_id) OR (private.current_app_role() = 'admin'::text)));


--
-- Name: patient_profiles; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.patient_profiles ENABLE ROW LEVEL SECURITY;

--
-- Name: patient_profiles patient_profiles_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY patient_profiles_read ON public.patient_profiles FOR SELECT TO authenticated USING (private.can_read_patient(user_id));


--
-- Name: patient_profiles patient_profiles_update_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY patient_profiles_update_own ON public.patient_profiles FOR UPDATE TO authenticated USING ((user_id = ( SELECT auth.uid() AS uid))) WITH CHECK ((user_id = ( SELECT auth.uid() AS uid)));


--
-- Name: patient_profiles patient_profiles_write_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY patient_profiles_write_own ON public.patient_profiles FOR INSERT TO authenticated WITH CHECK ((user_id = ( SELECT auth.uid() AS uid)));


--
-- Name: profiles; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

--
-- Name: profiles profiles_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY profiles_read ON public.profiles FOR SELECT TO authenticated USING ((private.can_read_patient(id) OR private.is_my_doctor(id)));


--
-- Name: profiles profiles_update_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY profiles_update_own ON public.profiles FOR UPDATE TO authenticated USING ((id = ( SELECT auth.uid() AS uid))) WITH CHECK ((id = ( SELECT auth.uid() AS uid)));


--
-- Name: symptom_reports; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.symptom_reports ENABLE ROW LEVEL SECURITY;

--
-- Name: symptom_reports symptom_reports_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY symptom_reports_read ON public.symptom_reports FOR SELECT TO authenticated USING (private.can_read_patient(patient_id));


--
-- Name: symptom_reports symptoms_insert_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY symptoms_insert_own ON public.symptom_reports FOR INSERT TO authenticated WITH CHECK (((patient_id = ( SELECT auth.uid() AS uid)) AND (source = ANY (ARRAY['patient_reported'::text, 'bystander'::text]))));


--
-- Name: trusted_contacts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.trusted_contacts ENABLE ROW LEVEL SECURITY;

--
-- Name: trusted_contacts trusted_contacts_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY trusted_contacts_read ON public.trusted_contacts FOR SELECT TO authenticated USING (private.can_read_patient(patient_id));


--
-- Name: wearable_samples; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.wearable_samples ENABLE ROW LEVEL SECURITY;

--
-- Name: wearable_samples wearable_samples_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY wearable_samples_read ON public.wearable_samples FOR SELECT TO authenticated USING (private.can_read_patient(patient_id));


--
-- Name: SCHEMA private; Type: ACL; Schema: -; Owner: -
--

GRANT USAGE ON SCHEMA private TO authenticated;


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: -
--

GRANT USAGE ON SCHEMA public TO postgres;
GRANT USAGE ON SCHEMA public TO anon;
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT USAGE ON SCHEMA public TO service_role;


--
-- Name: FUNCTION audit(); Type: ACL; Schema: private; Owner: -
--

GRANT ALL ON FUNCTION private.audit() TO authenticated;


--
-- Name: FUNCTION can_read_patient(patient uuid); Type: ACL; Schema: private; Owner: -
--

GRANT ALL ON FUNCTION private.can_read_patient(patient uuid) TO authenticated;


--
-- Name: FUNCTION current_app_role(); Type: ACL; Schema: private; Owner: -
--

GRANT ALL ON FUNCTION private.current_app_role() TO authenticated;


--
-- Name: FUNCTION enforce_roles(); Type: ACL; Schema: private; Owner: -
--

GRANT ALL ON FUNCTION private.enforce_roles() TO authenticated;


--
-- Name: FUNCTION handle_new_user(); Type: ACL; Schema: private; Owner: -
--

GRANT ALL ON FUNCTION private.handle_new_user() TO authenticated;


--
-- Name: FUNCTION is_assigned_doctor(patient uuid); Type: ACL; Schema: private; Owner: -
--

GRANT ALL ON FUNCTION private.is_assigned_doctor(patient uuid) TO authenticated;


--
-- Name: FUNCTION is_my_doctor(doctor uuid); Type: ACL; Schema: private; Owner: -
--

GRANT ALL ON FUNCTION private.is_my_doctor(doctor uuid) TO authenticated;


--
-- Name: FUNCTION is_valid_tz(tz text); Type: ACL; Schema: private; Owner: -
--

GRANT ALL ON FUNCTION private.is_valid_tz(tz text) TO authenticated;


--
-- Name: FUNCTION touch_updated_at(); Type: ACL; Schema: private; Owner: -
--

GRANT ALL ON FUNCTION private.touch_updated_at() TO authenticated;


--
-- Name: FUNCTION validate_measurement(); Type: ACL; Schema: private; Owner: -
--

GRANT ALL ON FUNCTION private.validate_measurement() TO authenticated;


--
-- Name: TABLE alert_measurements; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.alert_measurements TO service_role;
GRANT SELECT ON TABLE public.alert_measurements TO authenticated;


--
-- Name: TABLE alerts; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.alerts TO service_role;
GRANT SELECT ON TABLE public.alerts TO authenticated;


--
-- Name: TABLE audit_log; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.audit_log TO service_role;
GRANT SELECT ON TABLE public.audit_log TO authenticated;


--
-- Name: SEQUENCE audit_log_id_seq; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON SEQUENCE public.audit_log_id_seq TO anon;
GRANT ALL ON SEQUENCE public.audit_log_id_seq TO authenticated;
GRANT ALL ON SEQUENCE public.audit_log_id_seq TO service_role;


--
-- Name: TABLE body_measurements; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.body_measurements TO service_role;
GRANT SELECT,INSERT ON TABLE public.body_measurements TO authenticated;


--
-- Name: TABLE care_plans; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.care_plans TO service_role;
GRANT SELECT,INSERT,UPDATE ON TABLE public.care_plans TO authenticated;


--
-- Name: TABLE devices; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.devices TO service_role;
GRANT SELECT,INSERT,UPDATE ON TABLE public.devices TO authenticated;


--
-- Name: TABLE doctor_notes; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.doctor_notes TO service_role;
GRANT SELECT,INSERT,UPDATE ON TABLE public.doctor_notes TO authenticated;


--
-- Name: TABLE doctor_patient_assignments; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.doctor_patient_assignments TO service_role;
GRANT SELECT ON TABLE public.doctor_patient_assignments TO authenticated;


--
-- Name: TABLE emergency_events; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.emergency_events TO service_role;
GRANT SELECT,INSERT,UPDATE ON TABLE public.emergency_events TO authenticated;


--
-- Name: TABLE ingestion_batches; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.ingestion_batches TO service_role;
GRANT SELECT ON TABLE public.ingestion_batches TO authenticated;


--
-- Name: TABLE journal_entries; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.journal_entries TO service_role;
GRANT SELECT,INSERT ON TABLE public.journal_entries TO authenticated;


--
-- Name: COLUMN journal_entries.doctor_review_status; Type: ACL; Schema: public; Owner: -
--

GRANT UPDATE(doctor_review_status) ON TABLE public.journal_entries TO authenticated;


--
-- Name: COLUMN journal_entries.reviewed_by; Type: ACL; Schema: public; Owner: -
--

GRANT UPDATE(reviewed_by) ON TABLE public.journal_entries TO authenticated;


--
-- Name: COLUMN journal_entries.reviewed_at; Type: ACL; Schema: public; Owner: -
--

GRANT UPDATE(reviewed_at) ON TABLE public.journal_entries TO authenticated;


--
-- Name: TABLE lifestyle_logs; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.lifestyle_logs TO service_role;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.lifestyle_logs TO authenticated;


--
-- Name: TABLE measurements; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.measurements TO service_role;
GRANT SELECT,INSERT ON TABLE public.measurements TO authenticated;


--
-- Name: TABLE medication_adherence_events; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.medication_adherence_events TO service_role;
GRANT SELECT,INSERT ON TABLE public.medication_adherence_events TO authenticated;


--
-- Name: TABLE medications; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.medications TO service_role;
GRANT SELECT,INSERT,UPDATE ON TABLE public.medications TO authenticated;


--
-- Name: TABLE ml_predictions; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.ml_predictions TO service_role;
GRANT SELECT ON TABLE public.ml_predictions TO authenticated;


--
-- Name: TABLE patient_profiles; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.patient_profiles TO service_role;
GRANT SELECT,INSERT,UPDATE ON TABLE public.patient_profiles TO authenticated;


--
-- Name: TABLE profiles; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.profiles TO service_role;
GRANT SELECT ON TABLE public.profiles TO authenticated;


--
-- Name: COLUMN profiles.display_name; Type: ACL; Schema: public; Owner: -
--

GRANT UPDATE(display_name) ON TABLE public.profiles TO authenticated;


--
-- Name: COLUMN profiles.timezone; Type: ACL; Schema: public; Owner: -
--

GRANT UPDATE(timezone) ON TABLE public.profiles TO authenticated;


--
-- Name: COLUMN profiles.preferred_language; Type: ACL; Schema: public; Owner: -
--

GRANT UPDATE(preferred_language) ON TABLE public.profiles TO authenticated;


--
-- Name: TABLE symptom_reports; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.symptom_reports TO service_role;
GRANT SELECT,INSERT ON TABLE public.symptom_reports TO authenticated;


--
-- Name: TABLE trusted_contacts; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.trusted_contacts TO service_role;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.trusted_contacts TO authenticated;


--
-- Name: TABLE wearable_samples; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.wearable_samples TO service_role;
GRANT SELECT ON TABLE public.wearable_samples TO authenticated;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: public; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO postgres;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO service_role;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: public; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON SEQUENCES TO postgres;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON SEQUENCES TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON SEQUENCES TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON SEQUENCES TO service_role;


--
-- Name: DEFAULT PRIVILEGES FOR FUNCTIONS; Type: DEFAULT ACL; Schema: public; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON FUNCTIONS TO postgres;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON FUNCTIONS TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON FUNCTIONS TO service_role;


--
-- Name: DEFAULT PRIVILEGES FOR FUNCTIONS; Type: DEFAULT ACL; Schema: public; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON FUNCTIONS TO postgres;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON FUNCTIONS TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON FUNCTIONS TO service_role;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: public; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO service_role;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: public; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON TABLES TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON TABLES TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON TABLES TO service_role;


--
-- PostgreSQL database dump complete
--



-- ---------------------------------------------------------------- auth structure (from 20261029120000_core_schema.sql)
-- Supabase Auth (email/password) owns auth.users. Each new auth user gets a public.profiles row
-- (same id, role 'patient'); doctor/admin roles are set only with the service role.
CREATE TRIGGER on_auth_user_created AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION private.handle_new_user();
