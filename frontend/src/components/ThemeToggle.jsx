import { Sun, Moon } from "lucide-react";
import { useTheme } from "@/lib/theme";

export default function ThemeToggle() {
    const { theme, toggleTheme } = useTheme();

    return (
        <button
            onClick={toggleTheme}
            data-testid="theme-toggle-btn"
            aria-label="Toggle dark mode"
            className="w-9 h-9 flex items-center justify-center border border-border hover:bg-[#F3F4F6] dark:hover:bg-white/10 transition-colors"
        >
            {theme === "dark" ? (
                <Sun className="w-4 h-4" strokeWidth={1.75} />
            ) : (
                <Moon className="w-4 h-4" strokeWidth={1.75} />
            )}
        </button>
    );
}