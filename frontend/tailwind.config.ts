import type { Config } from "tailwindcss";
export default { content:["./app/**/*.{js,ts,jsx,tsx}","./components/**/*.{js,ts,jsx,tsx}"], theme:{extend:{colors:{navy:"#0d2745",ink:"#17233c",sky:"#2f80ed",teal:"#16a394",mist:"#f4f7fb"},boxShadow:{card:"0 10px 30px rgba(13,39,69,.07)"}}},plugins:[] } satisfies Config;
