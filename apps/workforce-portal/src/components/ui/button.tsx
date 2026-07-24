'use client';

import {Slot} from '@radix-ui/react-slot';
import type {ButtonHTMLAttributes, ReactNode} from 'react';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  readonly asChild?: boolean;
  readonly children: ReactNode;
};

export function Button({asChild = false, className = '', ...props}: ButtonProps) {
  const Component = asChild ? Slot : 'button';
  return <Component className={`button ${className}`.trim()} {...props} />;
}
