import { useMutation, useQueryClient } from '@tanstack/react-query'
import { syncSingleRide, fetchSyncStatus } from '../lib/api'

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

export function useSyncSingleRide() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (icuId: string) => {
      const res = await syncSingleRide(icuId)
      if (!res.sync_id) return res

      let attempts = 0
      while (attempts < 120) { // 60 seconds max
        await sleep(500)
        attempts++
        const status = await fetchSyncStatus(res.sync_id)
        if (status.status === 'completed' || status.status === 'success') {
          return status
        }
        if (status.status === 'failed' || status.status === 'error') {
          throw new Error((status as any).errors || status.detail || 'Sync failed')
        }
      }
      throw new Error('Sync timed out waiting for completion')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rides'] })
      queryClient.invalidateQueries({ queryKey: ['ride'] })
    }
  })
}
