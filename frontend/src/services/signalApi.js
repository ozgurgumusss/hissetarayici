import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API_BASE = `${BACKEND_URL}/api`;

const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: 45000,
});

export const fetchConfig = async () => {
  const { data } = await apiClient.get("/config");
  return data;
};

export const fetchScannerState = async () => {
  const { data } = await apiClient.get("/scanner/state");
  return data;
};

export const runScanner = async () => {
  const { data } = await apiClient.post("/scanner/run");
  return data;
};

export const fetchSignals = async ({ market = "ALL", action = "ALL", limit = 200, search = "" }) => {
  const params = { market, action, limit };
  if (search?.trim()) {
    params.search = search.trim().toUpperCase();
  }
  const { data } = await apiClient.get("/signals", { params });
  return data;
};

export const fetchSignalDetail = async (symbol) => {
  const { data } = await apiClient.get(`/signals/${symbol}`);
  return data;
};

export const explainSignal = async (symbol) => {
  const { data } = await apiClient.post(`/signals/${symbol}/explain`);
  return data;
};
