import { useState, useEffect, useCallback } from 'react';
import { supabase } from './supabase';
import { useAuth } from './auth';

export function useFavorites() {
  const { user } = useAuth();
  const [favorites, setFavorites] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) {
      setFavorites([]);
      setLoading(false);
      return;
    }

    async function loadFavorites() {
      if (!user) return;
      const { data, error } = await supabase
        .from('favorites')
        .select('restaurant_id')
        .eq('user_id', user.id);

      if (!error && data) {
        setFavorites(data.map((f: { restaurant_id: number }) => f.restaurant_id));
      }
      setLoading(false);
    }

    loadFavorites();
  }, [user]);

  const isFavorite = useCallback((restaurantId: number) => {
    return favorites.includes(restaurantId);
  }, [favorites]);

  const toggleFavorite = useCallback(async (restaurantId: number) => {
    if (!user) return false;

    if (isFavorite(restaurantId)) {
      // 取消收藏
      const { error } = await supabase
        .from('favorites')
        .delete()
        .eq('user_id', user.id)
        .eq('restaurant_id', restaurantId);

      if (!error) {
        setFavorites(prev => prev.filter(id => id !== restaurantId));
        return true;
      }
    } else {
      // 添加收藏
      const { error } = await supabase
        .from('favorites')
        .insert({ user_id: user.id, restaurant_id: restaurantId });

      if (!error) {
        setFavorites(prev => [...prev, restaurantId]);
        return true;
      }
    }
    return false;
  }, [user, isFavorite]);

  return { favorites, loading, isFavorite, toggleFavorite };
}
