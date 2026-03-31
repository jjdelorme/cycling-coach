import { useMutation, useQueryClient } from '@tanstack/react-query'
import { syncSingleRide } from '../lib/api'

export function useSyncSingleRide() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (icuId: string) => {
      const res = await syncSingleRide(icuId)
      return res
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rides'] })
    }
  })
}
