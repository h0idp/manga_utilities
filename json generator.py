import json
import os
import io
import tkinter as tk
from tkinter import filedialog, messagebox, Toplevel, Listbox, Label, Scrollbar, StringVar
import requests
from PIL import Image, ImageTk
from typing import List, Dict, Any, Optional


class MangaJSONGenerator:
    def __init__(self, root):
        self.root = root
        self.root.title("Generador de JSON para Manga")
        self.root.geometry("520x600")
        
        # Definir fuentes y estilos
        self.label_font = ("Segoe UI", 11, "bold")
        
        # Variable para rastrear si el manga es para adultos
        self.is_adult = False
        
        # Construir la interfaz
        self.setup_ui()
    
    def setup_ui(self):
        """Configurar todos los elementos de la interfaz de usuario"""
        # Título y búsqueda
        title_frame = tk.Frame(self.root)
        title_frame.pack(pady=5)
        
        tk.Label(title_frame, text="Título:", font=self.label_font).pack(side=tk.LEFT)
        self.title_entry = tk.Entry(title_frame, width=35)
        self.title_entry.pack(side=tk.LEFT, padx=5)
        search_button = tk.Button(title_frame, text="🔍", command=self.search_anilist)
        search_button.pack(side=tk.LEFT)
        
        # Autor y Artista
        tk.Label(self.root, text="Autor:", font=self.label_font).pack()
        self.author_entry = tk.Entry(self.root, width=50)
        self.author_entry.pack(pady=3)
        
        tk.Label(self.root, text="Artista:", font=self.label_font).pack()
        self.artist_entry = tk.Entry(self.root, width=50)
        self.artist_entry.pack(pady=3)
        
        # Descripción
        tk.Label(self.root, text="Descripción:", font=self.label_font).pack()
        self.description_text = tk.Text(self.root, width=50, height=5)
        self.description_text.pack(pady=5)
        
        # Géneros
        tk.Label(self.root, text="Géneros (separados por coma):", font=self.label_font).pack()
        self.genre_entry = tk.Entry(self.root, width=50)
        self.genre_entry.pack(pady=3)
        
        # Estado
        tk.Label(self.root, text="Estado (1=Finalizado, 0=En curso, o cualquier número):", font=self.label_font).pack()
        self.status_entry = tk.Entry(self.root, width=10)
        self.status_entry.insert(0, "1")  # Valor predeterminado
        self.status_entry.pack(pady=3)
        
        # Carpeta
        tk.Label(self.root, text="Carpeta de destino:", font=self.label_font).pack(pady=3)
        folder_frame = tk.Frame(self.root)
        folder_frame.pack()
        self.folder_entry = tk.Entry(folder_frame, width=40)
        self.folder_entry.pack(side=tk.LEFT, padx=5)
        folder_button = tk.Button(folder_frame, text="📁", command=self.select_folder)
        folder_button.pack(side=tk.LEFT)
        
        # Botón Guardar
        generate_button = tk.Button(
            self.root, 
            text="Guardar JSON", 
            command=self.generate_json, 
            width=25, 
            font=("Segoe UI", 11, "bold")
        )
        generate_button.pack(pady=20)
    
    def search_anilist(self):
        """Buscar manga en AniList API utilizando GraphQL"""
        title = self.title_entry.get()
        if not title:
            messagebox.showwarning("Advertencia", "Por favor, ingrese un título antes de buscar.")
            return

        query = """
        query ($search: String) {
          Page(perPage: 10) {
            media(search: $search, type: MANGA) {
              title {
                romaji
                english
              }
              description
              genres
              status
              isAdult
              coverImage {
                large
              }
              staff {
                edges {
                  node {
                    name {
                      full
                    }
                  }
                  role
                }
              }
            }
          }
        }
        """

        variables = {"search": title}
        url = "https://graphql.anilist.co"
        
        try:
            response = requests.post(url, json={"query": query, "variables": variables})
            response.raise_for_status()  # Lanzar excepción para códigos de error HTTP
            
            results = response.json().get("data", {}).get("Page", {}).get("media", [])
            if not results:
                messagebox.showinfo("Información", "No se encontraron resultados para la búsqueda.")
                return
                
            self.show_results_window(results)
            
        except requests.RequestException as e:
            messagebox.showerror("Error de conexión", f"No se pudo conectar a AniList: {str(e)}")
        except (KeyError, ValueError) as e:
            messagebox.showerror("Error", f"Error al procesar la respuesta: {str(e)}")

    def show_results_window(self, results: List[Dict[str, Any]]):
        """Mostrar ventana de resultados de búsqueda"""
        result_window = Toplevel(self.root)
        result_window.title("Resultados de búsqueda")
        result_window.geometry("520x650")
        result_window.transient(self.root)  # Hacer que la ventana sea dependiente de la principal
        result_window.grab_set()  # Forzar que la ventana tenga foco
        result_window.resizable(True, True)  # Permitir redimensionamiento
        
        # Usando Grid para mejor control del layout
        result_window.grid_rowconfigure(0, weight=0)  # Lista
        result_window.grid_rowconfigure(1, weight=0)  # Imagen
        result_window.grid_rowconfigure(2, weight=1)  # Descripción (expandible)
        result_window.grid_rowconfigure(3, weight=0)  # Botones
        result_window.grid_columnconfigure(0, weight=1)

        # Frame superior para la lista
        top_frame = tk.Frame(result_window)
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        
        # Configurar listbox y scrollbar
        list_frame = tk.Frame(top_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        listbox = Listbox(list_frame, width=50, height=10, yscrollcommand=scrollbar.set, font=("Segoe UI", 10))
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)

        # Frame para la imagen (tamaño fijo)
        image_frame = tk.Frame(result_window, height=300)
        image_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        image_frame.pack_propagate(False)  # Mantener tamaño fijo
        
        image_label = Label(image_frame)
        image_label.pack(expand=True)
        
        # Frame para la descripción con scrollbar (expandible)
        desc_frame = tk.Frame(result_window)
        desc_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        
        desc_canvas = tk.Canvas(desc_frame)
        desc_scrollbar = Scrollbar(desc_frame, orient="vertical", command=desc_canvas.yview)
        desc_scrollable_frame = tk.Frame(desc_canvas)
        
        # Configurar el frame scrollable
        desc_scrollable_frame.bind(
            "<Configure>",
            lambda e: desc_canvas.configure(scrollregion=desc_canvas.bbox("all"))
        )
        
        desc_canvas.create_window((0, 0), window=desc_scrollable_frame, anchor="nw")
        desc_canvas.configure(yscrollcommand=desc_scrollbar.set)
        
        desc_canvas.pack(side="left", fill="both", expand=True)
        desc_scrollbar.pack(side="right", fill="y")
        
        description_label = Label(desc_scrollable_frame, text="", wraplength=450, justify=tk.LEFT, anchor="nw")
        description_label.pack(fill="both", expand=True, padx=5, pady=5)

        # Frame para los botones (siempre en la parte inferior)
        button_frame = tk.Frame(result_window)
        button_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=10)
        button_frame.columnconfigure(0, weight=1)  # Centrar botones
        
        # Insertar títulos en la lista
        for item in results:
            title = item["title"]["romaji"]
            if item["title"].get("english") and item["title"]["english"] != title:
                title += f" ({item['title']['english']})"
            # Marcar títulos para adultos
            if item.get("isAdult", False):
                title += " [NSFW]"
            listbox.insert(tk.END, title)

        def update_preview(event):
            """Actualizar la vista previa al seleccionar un elemento"""
            selected_index = listbox.curselection()
            if not selected_index:
                return
                
            selected_data = results[selected_index[0]]
            image_url = selected_data["coverImage"]["large"]
            
            # Mostrar descripción
            desc = selected_data.get("description", "Sin descripción disponible")
            if desc:
                # Eliminar etiquetas HTML básicas
                desc = desc.replace("<br>", "\n").replace("<i>", "").replace("</i>", "")
                # Ya no necesitamos limitar la longitud porque tenemos scroll
            description_label.config(text=desc)
            
            # Hacer scroll al inicio de la descripción
            desc_canvas.yview_moveto(0)
            
            # Cargar imagen
            try:
                response = requests.get(image_url)
                response.raise_for_status()
                image = Image.open(io.BytesIO(response.content))
                image = image.resize((200, 300))
                photo = ImageTk.PhotoImage(image)
                image_label.configure(image=photo)
                image_label.image = photo  # Mantener referencia
            except Exception as e:
                image_label.config(image="")
                messagebox.showerror("Error", f"No se pudo cargar la imagen: {str(e)}")

        def select_item():
            """Seleccionar el manga elegido y poblar el formulario principal"""
            selected_index = listbox.curselection()
            if not selected_index:
                messagebox.showwarning("Advertencia", "Por favor, seleccione un manga de la lista.")
                return
                
            selected_data = results[selected_index[0]]
            
            # Actualizar campos del formulario
            self.title_entry.delete(0, tk.END)
            self.title_entry.insert(0, selected_data["title"]["romaji"])
            
            self.description_text.delete("1.0", tk.END)
            if selected_data.get("description"):
                # Limpiar HTML básico
                clean_desc = selected_data["description"].replace("<br>", "\n")
                clean_desc = clean_desc.replace("<i>", "").replace("</i>", "")
                self.description_text.insert("1.0", clean_desc)
            
            self.genre_entry.delete(0, tk.END)
            self.genre_entry.insert(0, ", ".join(selected_data.get("genres", [])))
            
            # Establecer estado en el nuevo campo de entrada
            self.status_entry.delete(0, tk.END)
            self.status_entry.insert(0, "1" if selected_data.get("status") == "FINISHED" else "0")

            # Buscar autor y artista en el staff
            author = ""
            artist = ""
            for staff in selected_data.get("staff", {}).get("edges", []):
                role = staff.get("role", "")
                name = staff.get("node", {}).get("name", {}).get("full", "")
                if not name:
                    continue
                    
                if "Story" in role:
                    author = name
                if "Art" in role:
                    artist = name

            self.author_entry.delete(0, tk.END)
            self.author_entry.insert(0, author)

            self.artist_entry.delete(0, tk.END)
            self.artist_entry.insert(0, artist)
            
            # Guardar el estado isAdult para usarlo en la generación del JSON
            self.is_adult = selected_data.get("isAdult", False)
            
            result_window.destroy()

        # Configurar eventos y botones
        listbox.bind("<<ListboxSelect>>", update_preview)
        
        # Crear un contenedor central para los botones
        center_button_frame = tk.Frame(button_frame)
        center_button_frame.grid(row=0, column=0)
        
        tk.Button(
            center_button_frame, 
            text="Seleccionar", 
            command=select_item, 
            width=15, 
            font=("Segoe UI", 10, "bold")
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            center_button_frame,
            text="Cancelar",
            command=result_window.destroy,
            width=15
        ).pack(side=tk.LEFT, padx=5)

    def select_folder(self):
        """Seleccionar carpeta de destino"""
        folder_selected = filedialog.askdirectory()
        if not folder_selected:
            return
            
        self.folder_entry.delete(0, tk.END)
        self.folder_entry.insert(0, folder_selected)
        
        # Auto-completar el título con el nombre de la carpeta si está vacío
        if not self.title_entry.get():
            folder_name = os.path.basename(folder_selected)
            self.title_entry.insert(0, folder_name)

    def generate_json(self):
        """Generar y guardar el archivo JSON con los datos del manga"""
        folder_path = self.folder_entry.get().strip()
        if not folder_path:
            messagebox.showwarning("Advertencia", "Por favor, seleccione una carpeta primero.")
            return
            
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showwarning("Advertencia", "El título no puede estar vacío.")
            return

        # Obtener el valor del estado
        status_value = self.status_entry.get().strip()
        # Usar valor predeterminado si está vacío
        if not status_value:
            status_value = "1"

        # Procesar etiquetas/géneros - como una lista simple de strings
        genres = [tag.strip() for tag in self.genre_entry.get().split(",") if tag.strip()]
        
        # Añadir etiqueta NSFW si el manga es para adultos
        if self.is_adult and "NSFW" not in genres:
            genres.append("NSFW")
        
        # Preparar datos para el JSON con la nueva estructura
        data = {
            "title": title,
            "author": self.author_entry.get().strip(),
            "artist": self.artist_entry.get().strip(),
            "description": self.description_text.get("1.0", tk.END).strip(),
            "genre": genres,
            "status": status_value
        }

        file_path = os.path.join(folder_path, "details.json")
        
        try:
            with open(file_path, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=4, ensure_ascii=False)
            messagebox.showinfo("Éxito", f"Archivo JSON guardado en:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar el archivo:\n{str(e)}")


def main():
    """Función principal para iniciar la aplicación"""
    try:
        # Verificar dependencias
        dependencies = [requests, Image]
        
        root = tk.Tk()
        app = MangaJSONGenerator(root)
        root.mainloop()
    except ImportError as e:
        print(f"Error: Falta una dependencia requerida: {e}")
        print("Asegúrate de tener instalado: requests, Pillow")
    except Exception as e:
        print(f"Error inesperado al iniciar la aplicación: {e}")


if __name__ == "__main__":
    main()