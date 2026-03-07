import "@/App.css";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ThemeProvider } from "next-themes";
import DashboardPage from "@/pages/DashboardPage";
import { Toaster } from "@/components/ui/sonner";

function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="dark" forcedTheme="dark" enableSystem={false}>
      <div className="App min-h-screen bg-background text-foreground" data-testid="app-root-container">
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
          </Routes>
        </BrowserRouter>
        <Toaster position="top-right" />
      </div>
    </ThemeProvider>
  );
}

export default App;
