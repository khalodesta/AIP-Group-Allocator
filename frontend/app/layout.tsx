import "./globals.css";
import {Toaster} from "sonner";
export const metadata={title:"AIP Smart Group Allocator",description:"Intelligent onboarding and collaboration platform"};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}<Toaster position="top-right" richColors closeButton visibleToasts={4}/></body></html>}
