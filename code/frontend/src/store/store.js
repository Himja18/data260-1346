import { configureStore } from "@reduxjs/toolkit";
import incidentsReducer from "./incidentsSlice.js";

export const store = configureStore({
  reducer: {
    incidents: incidentsReducer,
  },
});
