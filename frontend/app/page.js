import Image from "next/image";
import ASLVoiceClient from "@/components/ASLVoiceClient.jsx";

export default function Home() {
  return (
    <div className="flex flex-col items-center justify-center mt-8">
    <ASLVoiceClient />
    </div>
  );
}
