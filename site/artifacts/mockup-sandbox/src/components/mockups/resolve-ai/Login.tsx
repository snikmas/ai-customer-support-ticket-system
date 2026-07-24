import React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { AlertCircle, EyeOff } from 'lucide-react';

export default function Login() {
  return (
    <div className="min-h-screen w-full bg-[#f4f5f7] flex flex-col items-center justify-center font-sans text-slate-900">
      <div className="w-full max-w-[400px]">
        <div className="flex justify-center mb-8">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-blue-600 rounded-sm"></div>
            <span className="font-semibold text-xl tracking-tight text-slate-900">ResolveAI</span>
          </div>
        </div>

        <Card className="w-full bg-white border-[#e2e4e7] shadow-sm rounded-xl overflow-hidden">
          <CardContent className="p-8 pt-8">
            <div className="text-center mb-6">
              <h1 className="text-lg font-medium text-slate-900">Customer support, resolved.</h1>
            </div>

            <div className="bg-red-50 border border-red-200 text-red-600 rounded-md p-3 flex items-start gap-2.5 mb-6">
              <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
              <span className="text-[14px] font-medium">Invalid credentials. Please try again.</span>
            </div>

            <form className="space-y-4" onSubmit={e => e.preventDefault()}>
              <div className="space-y-1.5">
                <label className="text-[15px] font-medium text-slate-900">Email or nickname</label>
                <Input
                  type="email"
                  defaultValue="jake.morris@resolveai.com"
                  className="border-[#e2e4e7] focus-visible:ring-blue-600 shadow-none h-10 text-[15px]"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-[15px] font-medium text-slate-900">Password</label>
                <div className="relative">
                  <Input
                    type="password"
                    defaultValue="••••••••"
                    className="border-[#e2e4e7] focus-visible:ring-blue-600 shadow-none pr-10 h-10 text-[15px]"
                  />
                  <button type="button" className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                    <EyeOff className="w-4 h-4" />
                  </button>
                </div>
              </div>

              <div className="pt-2">
                <Button className="w-full bg-blue-600 hover:bg-blue-700 text-white shadow-none h-10 font-medium text-[15px]">
                  Sign in
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <div className="mt-8 flex justify-center items-center gap-2 text-slate-500">
          <div className="w-2 h-2 rounded-full bg-green-500"></div>
          <span className="text-[13px] font-medium">API and dependencies operational</span>
        </div>
      </div>
    </div>
  );
}