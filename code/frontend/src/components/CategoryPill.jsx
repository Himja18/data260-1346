const KNOWN = {
  delay: "pill-delay",
  breakdown: "pill-breakdown",
  accident: "pill-accident",
  "service change": "pill-service",
};

export default function CategoryPill({ category }) {
  const cls = KNOWN[category.toLowerCase()] || "";
  return <span className={`pill ${cls}`}>{category}</span>;
}
