// Redux slice for the primary entity: transit incidents.
import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { client, toError } from "./client.js";

// ---- Async thunks: one per FastAPI endpoint ----------------------------
export const fetchIncidents = createAsyncThunk(
  "incidents/fetch",
  async (limit = 50, { rejectWithValue }) => {
    try {
      const res = await client.get("/incidents", { params: { limit } });   // GET list
      return res.data;
    } catch (err) {
      return rejectWithValue(toError(err));
    }
  }
);

export const createIncident = createAsyncThunk(
  "incidents/create",
  async (data, { rejectWithValue }) => {
    try {
      const res = await client.post("/incidents", data);                    // POST
      return res.data;
    } catch (err) {
      return rejectWithValue(toError(err));
    }
  }
);

export const updateIncident = createAsyncThunk(
  "incidents/update",
  async ({ id, data }, { rejectWithValue }) => {
    try {
      const res = await client.put(`/incidents/${id}`, data);               // PUT /{id}
      return res.data;
    } catch (err) {
      return rejectWithValue(toError(err));
    }
  }
);

export const deleteIncident = createAsyncThunk(
  "incidents/delete",
  async (id, { rejectWithValue }) => {
    try {
      await client.delete(`/incidents/${id}`);                              // DELETE /{id}
      return Number(id);
    } catch (err) {
      return rejectWithValue(toError(err));
    }
  }
);

// ---- Slice ----------------------------------------------------------------
const initialState = {
  items: [],
  status: "idle",       // idle | loading | ready | error   (list loading)
  error: null,          // { status, message } from the last failed thunk
  lastAction: null,     // short message for the UI after create/update/delete
};

const incidentsSlice = createSlice({
  name: "incidents",
  initialState,
  reducers: {
    clearIncidents: () => initialState,                 // on logout
    clearMessage: (state) => { state.lastAction = null; state.error = null; },
  },
  extraReducers: (builder) => {
    builder
      // fetch
      .addCase(fetchIncidents.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchIncidents.fulfilled, (state, action) => {
        state.status = "ready";
        state.items = action.payload;
      })
      .addCase(fetchIncidents.rejected, (state, action) => {
        state.status = "error";
        state.error = action.payload;
      })
      // create: newest first, so the new record appears at the top immediately
      .addCase(createIncident.fulfilled, (state, action) => {
        state.items.unshift(action.payload);
        state.lastAction = `Created ${action.payload.incident_code}`;
        state.error = null;
      })
      // update: replace the record in place
      .addCase(updateIncident.fulfilled, (state, action) => {
        const i = state.items.findIndex((x) => x.id === action.payload.id);
        if (i !== -1) state.items[i] = action.payload;
        else state.items.unshift(action.payload);
        state.lastAction = `Updated ${action.payload.incident_code}`;
        state.error = null;
      })
      // delete: remove from state, no refetch needed
      .addCase(deleteIncident.fulfilled, (state, action) => {
        state.items = state.items.filter((x) => x.id !== action.payload);
        state.lastAction = `Deleted incident #${action.payload}`;
        state.error = null;
      })
      // shared error handling for create / update / delete
      .addMatcher(
        (a) => a.type.startsWith("incidents/") && a.type.endsWith("/rejected")
               && !a.type.startsWith("incidents/fetch"),
        (state, action) => { state.error = action.payload; }
      );
  },
});

export const { clearIncidents, clearMessage } = incidentsSlice.actions;
export default incidentsSlice.reducer;

// Selectors
export const selectIncidents = (s) => s.incidents.items;
export const selectIncidentById = (id) => (s) =>
  s.incidents.items.find((x) => x.id === Number(id));
