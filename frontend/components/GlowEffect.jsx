'use client'
import React, { useState, useEffect } from "react";



const GlowBackground = () => {
  const [position, setPosition] = useState({ x: 540, y: 340 });

  useEffect(() => {
    const handleMouseMove = (e) => {
      setPosition({ x: e.clientX, y: e.clientY });
    };

    window.addEventListener("mousemove", handleMouseMove);
    
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      
    };
  }, []);

  return (
    <div
      className="fixed inset-0 h-lvh w-lvw pointer-events-none "
      style={{
        zIndex: -1, // Push the glow effect behind everything
      }}
    >
 <div
        className="absolute w-[24rem] h-[24rem] rounded-full pointer-events-none"
        style={{
          left: position.x,
          top: position.y,
          transform: "translate(-50%, -50%)",
          background: `radial-gradient(circle at ${position.x}px ${position.y}px,rgba(35, 35, 35, 0.08),transparent )`,
          transition: 'top 0.2 ease, left 0.2 ease'
          
        }}
      ></div>
      <div
        className="absolute w-[48rem] h-[48rem] rounded-full pointer-events-none"
        style={{
          left: position.x,
          top: position.y,
          transform: "translate(-50%, -50%)",
          background: `radial-gradient(circle at ${position.x}px ${position.y}px,rgba(0, 102, 51, 0.08),transparent )`,
          
        }}
      ></div>
      <div
        className="absolute w-[72rem] h-[72rem] rounded-full pointer-events-none"
        style={{
          left: position.x,
          top: position.y,
          transform: "translate(-50%, -50%)",
          background: `radial-gradient(circle at ${position.x}px ${position.y}px,rgba(0, 60, 255, 0.08),transparent )`,
          
        }}
      ></div>
      <div
        className="absolute w-[96rem] h-[96rem] rounded-full pointer-events-none"
        style={{
          left: position.x,
          top: position.y,
          transform: "translate(-50%, -50%)",
          background: `radial-gradient(circle at ${position.x}px ${position.y}px,rgba(0, 60, 255, 0.08),transparent )`,
          
        }}
      ></div>
    
    </div>
  );
};

export default GlowBackground;