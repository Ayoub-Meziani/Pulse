export default function StatCard({ title, value, unit, description }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-6 transition duration-200 hover:-translate-y-1 hover:shadow-md">
      <p className="text-sm font-medium text-slate-500">
        {title}
      </p>

      <div className="mt-4 flex items-baseline gap-2">
        <p className="text-3xl font-bold tracking-tight text-slate-900">
          {value}
        </p>

        {unit && (
          <span className="text-sm font-medium text-slate-500">
            {unit}
          </span>
        )}
      </div>

      <p className="mt-3 text-sm leading-5 text-slate-500">
        {description}
      </p>
    </article>
  );
}