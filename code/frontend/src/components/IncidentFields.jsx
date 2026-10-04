// Editable fields shared by CreateRecord and UpdateRecord.
export const CATEGORIES = ["Delay", "Breakdown", "Accident", "Service Change"];

export default function IncidentFields({ form, setForm }) {
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  return (
    <>
      <div className="field">
        <label htmlFor="route_title">Route and incident</label>
        <input id="route_title" value={form.route_title} onChange={set("route_title")}
          placeholder="Route 5 - 15 min delay at Main St" minLength={3} maxLength={200}
          required autoFocus />
      </div>
      <div className="field">
        <label htmlFor="category">Category</label>
        <select id="category" value={form.category} onChange={set("category")} required>
          <option value="" disabled>Choose a category</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor="passengers_affected">Passengers affected</label>
        <input id="passengers_affected" type="number" min={0} max={100000}
          value={form.passengers_affected} onChange={set("passengers_affected")} />
      </div>
      <div className="field">
        <label htmlFor="line_id">Transit line ID (optional)</label>
        <input id="line_id" type="number" min={1} value={form.line_id ?? ""}
          onChange={set("line_id")} placeholder="e.g. 5" />
      </div>
    </>
  );
}

// Form state -> API payload (numbers as numbers, empty line -> null).
export function toPayload(form) {
  return {
    route_title: form.route_title.trim(),
    category: form.category,
    passengers_affected: Number(form.passengers_affected) || 0,
    line_id: form.line_id === "" || form.line_id == null ? null : Number(form.line_id),
  };
}
