export default function AlertCard({
  title,
  message,
  variant = "info",
}) {
  const variants = {
    info: {
      container: "border-blue-200 bg-blue-50",
      icon: "bg-blue-100 text-blue-700",
      title: "text-blue-900",
      message: "text-blue-800",
      symbol: "i",
    },

    warning: {
      container: "border-amber-200 bg-amber-50",
      icon: "bg-amber-100 text-amber-700",
      title: "text-amber-900",
      message: "text-amber-800",
      symbol: "!",
    },

    critical: {
      container: "border-red-200 bg-red-50",
      icon: "bg-red-100 text-red-700",
      title: "text-red-900",
      message: "text-red-800",
      symbol: "!",
    },
  };

  const style = variants[variant] ?? variants.info;

  return (
    <article
      role={variant === "critical" ? "alert" : "status"}
      className={`flex gap-4 rounded-2xl border p-5 ${style.container}`}
    >
      <div
        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full font-bold ${style.icon}`}
      >
        {style.symbol}
      </div>

      <div>
        <h3 className={`font-semibold ${style.title}`}>
          {title}
        </h3>

        <p className={`mt-1 text-sm leading-6 ${style.message}`}>
          {message}
        </p>
      </div>
    </article>
  );
}