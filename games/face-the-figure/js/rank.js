// The rank for c correct calls on a chain of n links. The ladder follows the chain's length, which is 8 to 10 by the day:
// every call right is always the top rank, one miss the second, then 70, 50 and 30 per cent.
export const RANKS = ["Apprentice", "Junior clerk", "Senior clerk", "Chief cashier", "Auditor", "Comptroller"];
export function rankOf(c, n) {
  const cuts = [0, Math.ceil(n * 0.3), Math.ceil(n * 0.5), Math.min(Math.ceil(n * 0.7), n - 2), n - 1, n];
  return RANKS[cuts.filter((k) => c >= k).length - 1];
}
