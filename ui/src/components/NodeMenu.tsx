import { Divider, ListItemIcon, ListItemText, Menu, MenuItem } from '@mui/material'
import UnfoldMoreIcon from '@mui/icons-material/UnfoldMore'
import UnfoldLessIcon from '@mui/icons-material/UnfoldLess'
import AccountTreeIcon from '@mui/icons-material/AccountTree'
import NorthIcon from '@mui/icons-material/North'
import BoltIcon from '@mui/icons-material/Bolt'
import AddIcon from '@mui/icons-material/AddCircleOutlineOutlined'
import EditIcon from '@mui/icons-material/Edit'
import RouteIcon from '@mui/icons-material/Route'
import CenterFocusStrongIcon from '@mui/icons-material/CenterFocusStrong'
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import CableIcon from '@mui/icons-material/Cable'
import type { GNode } from '../api'

export type MenuAction =
  | 'expand' | 'expand3' | 'collapse' | 'parents' | 'provision' | 'add' | 'edit' | 'trace' | 'path-root'
  | 'focus' | 'hide' | 'netbox' | 'cable-trace'

export default function NodeMenu({ anchor, node, expanded, onClose, onAction }: {
  anchor: { x: number; y: number } | null
  node: GNode | null
  expanded: boolean
  onClose: () => void
  onAction: (a: MenuAction) => void
}) {
  if (!node) return null
  const isOntPort = node.kind === 'interface' && node.props.device_role === 'ont'
  const item = (a: MenuAction, icon: React.ReactNode, text: string, secondary?: string) => (
    <MenuItem key={a} dense onClick={() => { onAction(a); onClose() }}>
      <ListItemIcon>{icon}</ListItemIcon>
      <ListItemText primary={text} secondary={secondary} />
    </MenuItem>
  )
  return (
    <Menu open={Boolean(anchor)} onClose={onClose} anchorReference="anchorPosition"
      anchorPosition={anchor ? { top: anchor.y, left: anchor.x } : undefined}>
      <MenuItem disabled dense><ListItemText primary={node.label} secondary={`${node.kind_title} · ${node.subtype}`} /></MenuItem>
      <Divider />
      {expanded
        ? item('collapse', <UnfoldLessIcon fontSize="small" />, 'Collapse')
        : item('expand', <UnfoldMoreIcon fontSize="small" />, 'Expand', node.degree ? `${node.degree} links` : undefined)}
      {item('expand3', <AccountTreeIcon fontSize="small" />, 'Expand 3 levels')}
      {item('parents', <NorthIcon fontSize="small" />, 'Reveal parents / referrers')}
      <Divider />
      {isOntPort && item('provision', <BoltIcon fontSize="small" color="warning" />, 'Provision service…')}
      {item('add', <AddIcon fontSize="small" />, 'Add child…')}
      {item('edit', <EditIcon fontSize="small" />, 'Edit…')}
      <Divider />
      {item('path-root', <RouteIcon fontSize="small" />, 'Path to region root')}
      {(node.kind === 'device' || node.kind === 'interface') && item('cable-trace', <CableIcon fontSize="small" />, 'Cable trace to core (BNG)')}
      {item('trace', <RouteIcon fontSize="small" />, 'Shortest path to… (click target)')}
      {item('focus', <CenterFocusStrongIcon fontSize="small" />, 'Focus neighbourhood')}
      {item('hide', <VisibilityOffIcon fontSize="small" />, 'Hide from canvas')}
      {item('netbox', <OpenInNewIcon fontSize="small" />, 'Open in NetBox')}
    </Menu>
  )
}
