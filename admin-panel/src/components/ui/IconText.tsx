import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

type IconTextProps = {
  icon: LucideIcon
  children: ReactNode
  iconClassName?: string
  className?: string
}

export function IconText({ icon: Icon, children, iconClassName = 'w-4 h-4 shrink-0', className = '' }: IconTextProps) {
  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`}>
      <Icon className={iconClassName} aria-hidden="true" />
      <span>{children}</span>
    </span>
  )
}

type IconHeadingProps = {
  icon: LucideIcon
  children: ReactNode
  as?: 'h2' | 'h3'
  iconClassName?: string
  className?: string
}

export function IconHeading({
  icon: Icon,
  children,
  as: Tag = 'h2',
  iconClassName = 'w-5 h-5 shrink-0',
  className = '',
}: IconHeadingProps) {
  return (
    <Tag className={`flex items-center gap-2 ${className}`}>
      <Icon className={iconClassName} aria-hidden="true" />
      <span>{children}</span>
    </Tag>
  )
}
