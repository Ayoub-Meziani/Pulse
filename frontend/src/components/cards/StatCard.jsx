export default function StatCard({ title, value, unit, description }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition hover:shadow-md">
      <p className="text-sm font-medium text-slate-500">
        {title}
      </p>

      <p className="mt-4 text-3xl font-bold text-slate-900">
        {value}
        <span className="ml-2 text-base font-medium text-slate-500">
          {unit}
        </span>
      </p>

      <p className="mt-3 text-sm text-slate-500">
        {description}
      </p>
    </article>
  );
}