export async function createClient() {
  return {
    auth: {
      async getUser() {
        return { data: { user: null } };
      },
    },
  };
}
