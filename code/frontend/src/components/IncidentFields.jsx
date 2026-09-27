// The two editable fields shared by CreateRecord and UpdateRecord.
export const CATEGORIES = ["Delay", "Breakdown", "Accident", "Service Change"];

export default function IncidentFields({ routeTitle, setRouteTitle, category, setCategory }) {
  return (
    <>
      <div className="field">
        <label htmlFor="route_title">Route and incident</label>
        <input
          id="route_title"
          value={routeTitle}
          onChange={(e) => setRouteTitle(e.target.value)}
          placeholder="Line 22 - Bus stalled on Main St"
          minLength={3}
          maxLength={200}
          required
          autoFocus
        />
      </div>
      <div className="field">
        <label htmlFor="category">Category</label>
        <input
          id="category"
          list="category-options"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="Delay, Breakdown, Accident, or Service Change"
          minLength={2}
          maxLength={50}
          required
        />
        <datalist id="category-options">
          {CATEGORIES.map((c) => <option key={c} value={c} />)}
        </datalist>
      </div>
    </>
  );
}
