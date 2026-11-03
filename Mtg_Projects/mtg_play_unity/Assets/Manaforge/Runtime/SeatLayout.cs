using System;
using UnityEngine;

namespace Manaforge.Play
{
    // Presentation geometry only. Seat count never defines gameplay legality.
    public static class SeatLayout
    {
        public static Vector3 Position(int seat, int count)
        {
            if (count < 2 || seat < 0 || seat >= count)
                throw new ArgumentOutOfRangeException(nameof(seat));
            float angle = -Mathf.PI / 2 + seat * 2 * Mathf.PI / count;
            return new Vector3(Mathf.Cos(angle) * 6, Mathf.Sin(angle) * 3, 0);
        }
    }
}
