import "@/styles/globals.css"
import React from "react";
export const metadata = {
  title: "ASL",
  description: "ASLtranslater",
};
// import { Toaster } from "@components/ui/toaster";
import GlowEffect from "@/components/GlowEffect";
export default function RootLayout({ children }) {
  return (
    <html lang="en">

      <body>
        
          
          <div className="main">
            
          </div>    
          <main className="app" >
            <GlowEffect/>
            
            {children}
            

          </main>

      </body>
      
    </html>
  );
}
