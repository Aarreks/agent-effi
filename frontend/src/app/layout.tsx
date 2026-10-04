import type { Metadata } from 'next';
import './globals.css';
import {StaffGate} from '@/components/StaffGate';
export const metadata:Metadata={title:'EffiGov · Voice Desk',description:'Local voice intake and case management demo'};
export default function RootLayout({children}:{children:React.ReactNode}) {return <html lang="en"><body><StaffGate>{children}</StaffGate></body></html>}
