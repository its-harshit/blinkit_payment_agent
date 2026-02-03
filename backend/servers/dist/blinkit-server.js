#!/usr/bin/env node
// Minimal MCP-compatible stdio server exposing a dummy Blinkit catalog.
import * as readline from "node:readline";

const catalog = [
  { id: "blk-001", name: "Amul Toned Milk 1L", category: "Dairy", price: 65, stock: 42, rating: 4.6 },
  { id: "blk-002", name: "Mother Dairy Curd 500g", category: "Dairy", price: 38, stock: 30, rating: 4.4 },
  { id: "blk-003", name: "Brown Bread 400g", category: "Bakery", price: 45, stock: 24, rating: 4.2 },
  { id: "blk-004", name: "Coca Cola 1.25L", category: "Beverages", price: 55, stock: 50, rating: 4.5 },
  { id: "blk-005", name: "Bananas (6 pcs)", category: "Fruits", price: 60, stock: 18, rating: 4.1 },
  { id: "blk-006", name: "Potato 1kg", category: "Vegetables", price: 35, stock: 60, rating: 4.0 },
  { id: "blk-007", name: "Aashirvaad Atta 5kg", category: "Staples", price: 295, stock: 14, rating: 4.7 },
  { id: "blk-008", name: "Maggi Masala Noodles 12x70g", category: "Packaged Food", price: 156, stock: 22, rating: 4.8 },
  { id: "blk-009", name: "Tata Tea Premium 1kg", category: "Beverages", price: 499, stock: 10, rating: 4.3 },
  { id: "blk-010", name: "Fortune Sunflower Oil 1L", category: "Oils", price: 149, stock: 26, rating: 4.4, keywords: ["sunflower oil", "refined oil", "cooking oil", "oil"] },
  { id: "blk-011", name: "Britannia Marie Gold 250g", category: "Bakery", price: 35, stock: 40, rating: 4.2 },
  { id: "blk-012", name: "Kellogg's Corn Flakes 875g", category: "Breakfast", price: 320, stock: 16, rating: 4.5 },
  { id: "blk-013", name: "Parle-G Biscuits 800g", category: "Bakery", price: 80, stock: 38, rating: 4.4 },
  { id: "blk-014", name: "Nescafe Classic 200g", category: "Beverages", price: 360, stock: 12, rating: 4.6 },
  { id: "blk-015", name: "Haldiram Aloo Bhujia 400g", category: "Snacks", price: 150, stock: 28, rating: 4.3 },
  { id: "blk-016", name: "Lay's Magic Masala 90g", category: "Snacks", price: 30, stock: 55, rating: 4.1 },
  { id: "blk-017", name: "Dettol Handwash Refill 750ml", category: "Personal Care", price: 135, stock: 25, rating: 4.5 },
  { id: "blk-018", name: "Colgate Strong Teeth 200g", category: "Personal Care", price: 110, stock: 33, rating: 4.4 },
  { id: "blk-019", name: "Surf Excel Matic Front Load 1kg", category: "Home Care", price: 245, stock: 20, rating: 4.6 },
  { id: "blk-020", name: "Lizol Disinfectant Floor Cleaner 2L", category: "Home Care", price: 320, stock: 18, rating: 4.5 },
  { id: "blk-021", name: "Tomato 1kg", category: "Vegetables", price: 32, stock: 70, rating: 4.2 },
  { id: "blk-022", name: "Onion 1kg", category: "Vegetables", price: 40, stock: 80, rating: 4.1, keywords: ["onions"] },
  { id: "blk-023", name: "Green Chili 100g", category: "Vegetables", price: 18, stock: 45, rating: 4.2, keywords: ["green chilli", "green chillies", "green chilies", "chili", "chilli"] },
  { id: "blk-024", name: "Ginger 250g", category: "Vegetables", price: 35, stock: 40, rating: 4.3 },
  { id: "blk-025", name: "Garlic 250g", category: "Vegetables", price: 28, stock: 50, rating: 4.4 },
  { id: "blk-026", name: "Fresh Coriander 100g", category: "Vegetables", price: 15, stock: 60, rating: 4.5, keywords: ["coriander leaves", "dhania"] },
  { id: "blk-027", name: "Fresh Mint 100g", category: "Vegetables", price: 18, stock: 30, rating: 4.4, keywords: ["mint leaves", "pudina"] },
  { id: "blk-028", name: "Paneer 200g", category: "Dairy", price: 85, stock: 25, rating: 4.6 },
  { id: "blk-029", name: "Basmati Rice 1kg", category: "Staples", price: 165, stock: 35, rating: 4.7 },
  { id: "blk-030", name: "Toor Dal 1kg", category: "Pulses", price: 145, stock: 30, rating: 4.5 },
  { id: "blk-031", name: "Chana Dal 1kg", category: "Pulses", price: 110, stock: 32, rating: 4.4 },
  { id: "blk-032", name: "Rajma (Red Kidney Beans) 1kg", category: "Pulses", price: 160, stock: 26, rating: 4.5 },
  { id: "blk-033", name: "Desi Ghee 500ml", category: "Dairy", price: 420, stock: 18, rating: 4.8, keywords: ["ghee", "desi ghee", "clarified butter"] },
  { id: "blk-034", name: "Mustard Oil 1L", category: "Oils", price: 180, stock: 22, rating: 4.6, keywords: ["mustard oil", "sarson oil", "sarson ka tel", "cooking oil", "oil"] },
  { id: "blk-035", name: "Cumin Seeds (Jeera) 200g", category: "Spices", price: 95, stock: 34, rating: 4.7 },
  { id: "blk-036", name: "Coriander Powder 200g", category: "Spices", price: 70, stock: 36, rating: 4.5 },
  { id: "blk-037", name: "Turmeric Powder 200g", category: "Spices", price: 68, stock: 38, rating: 4.6 },
  { id: "blk-038", name: "Red Chili Powder 200g", category: "Spices", price: 90, stock: 34, rating: 4.5 },
  { id: "blk-039", name: "Garam Masala 100g", category: "Spices", price: 95, stock: 28, rating: 4.6 },
  { id: "blk-040", name: "Asafoetida (Hing) 25g", category: "Spices", price: 65, stock: 20, rating: 4.4 },
  { id: "blk-041", name: "Black Pepper Whole 100g", category: "Spices", price: 120, stock: 24, rating: 4.6 },
  { id: "blk-042", name: "Mustard Seeds (Rai) 200g", category: "Spices", price: 60, stock: 30, rating: 4.4 },
  { id: "blk-043", name: "Bay Leaf (Tej Patta) 20g", category: "Spices", price: 25, stock: 40, rating: 4.3 },
  { id: "blk-044", name: "Cinnamon Stick 50g", category: "Spices", price: 55, stock: 26, rating: 4.5 },
  { id: "blk-045", name: "Green Cardamom 50g", category: "Spices", price: 185, stock: 18, rating: 4.7 },
  { id: "blk-046", name: "Cloves 50g", category: "Spices", price: 150, stock: 16, rating: 4.6 },
  { id: "blk-047", name: "Kasuri Methi 25g", category: "Spices", price: 40, stock: 28, rating: 4.4 },
  { id: "blk-048", name: "Star Anise 50g", category: "Spices", price: 90, stock: 22, rating: 4.6 },
  { id: "blk-049", name: "Black Cardamom Pods 50g", category: "Spices", price: 120, stock: 20, rating: 4.6 },
  { id: "blk-050", name: "Mace (Javitri) 25g", category: "Spices", price: 140, stock: 18, rating: 4.7 },
  { id: "blk-051", name: "Shahi Jeera 100g", category: "Spices", price: 85, stock: 24, rating: 4.5 },
  { id: "blk-052", name: "Fennel Seeds (Saunf) 200g", category: "Spices", price: 75, stock: 32, rating: 4.5 },
  { id: "blk-053", name: "Saffron 1g", category: "Spices", price: 320, stock: 12, rating: 4.8 },
  { id: "blk-054", name: "Biryani Masala 100g", category: "Spices", price: 110, stock: 30, rating: 4.7 },
  { id: "blk-055", name: "Fried Onions (Birista) 200g", category: "Ready to Cook", price: 140, stock: 28, rating: 4.5 },
  { id: "blk-056", name: "Kewra Water 200ml", category: "Essence", price: 60, stock: 25, rating: 4.4, keywords: ["kewra"] },
  { id: "blk-057", name: "Rose Water 200ml", category: "Essence", price: 55, stock: 25, rating: 4.4 },
  { id: "blk-058", name: "Whole Nutmeg 50g", category: "Spices", price: 95, stock: 20, rating: 4.5 },
  { id: "blk-059", name: "Khoya / Mawa 200g", category: "Dairy", price: 120, stock: 22, rating: 4.6 },
  { id: "blk-060", name: "Condensed Milk 400g", category: "Dairy", price: 145, stock: 26, rating: 4.5 },
  { id: "blk-061", name: "Fresh Cream 200ml", category: "Dairy", price: 75, stock: 30, rating: 4.6 },
  { id: "blk-062", name: "Unsalted Butter 500g", category: "Dairy", price: 285, stock: 18, rating: 4.6 },
  { id: "blk-063", name: "Mixed Dry Fruits 200g (Cashew, Almond, Raisin)", category: "Dry Fruits", price: 260, stock: 24, rating: 4.7, keywords: ["almond", "almonds", "badam", "dry fruits", "nuts", "cashew", "raisin", "kishmish"] },
  { id: "blk-064", name: "Carrot 1kg", category: "Vegetables", price: 28, stock: 70, rating: 4.3, keywords: ["carrot", "carrots", "gajar"] },
  { id: "blk-065", name: "Green Peas 500g", category: "Vegetables", price: 55, stock: 40, rating: 4.4 },
  { id: "blk-066", name: "Yogurt (Dahi) 500g", category: "Dairy", price: 45, stock: 34, rating: 4.5, keywords: ["curd"] },
  { id: "blk-067", name: "Tomato Puree 200g", category: "Packaged Food", price: 35, stock: 36, rating: 4.3 },
  { id: "blk-068", name: "Butter (Salted) 500g", category: "Dairy", price: 275, stock: 20, rating: 4.6 },
  { id: "blk-069", name: "Paneer Tikka Masala Paste 200g", category: "Ready to Cook", price: 120, stock: 18, rating: 4.4 },
  { id: "blk-070", name: "Premium Basmati Rice 5kg", category: "Staples", price: 950, stock: 14, rating: 4.8 },
  { id: "blk-071", name: "Kurkure Masala Munch 90g", category: "Snacks", price: 25, stock: 60, rating: 4.3, keywords: ["kurkure"] },
  { id: "blk-072", name: "Bingo Mad Angles 80g", category: "Snacks", price: 25, stock: 55, rating: 4.2 },
  { id: "blk-073", name: "Too Yumm Multigrain Chips 90g", category: "Snacks", price: 35, stock: 40, rating: 4.1 },
  { id: "blk-074", name: "Haldiram Moong Dal 200g", category: "Snacks", price: 65, stock: 38, rating: 4.5 },
  { id: "blk-075", name: "Bikaneri Bhujia 200g", category: "Snacks", price: 70, stock: 36, rating: 4.4 },
  { id: "blk-076", name: "Roasted Salted Almonds 200g", category: "Snacks", price: 320, stock: 24, rating: 4.7, keywords: ["almond", "almonds", "badam", "roasted almond", "salted almond", "sliced almond"] },
  { id: "blk-077", name: "Trail Mix Seeds & Nuts 200g", category: "Snacks", price: 260, stock: 22, rating: 4.6 },
  { id: "blk-078", name: "Popcorn Ready-to-Eat 60g", category: "Snacks", price: 35, stock: 42, rating: 4.2 },
  { id: "blk-079", name: "Nacho Chips (Cheese) 150g", category: "Snacks", price: 90, stock: 28, rating: 4.3 },
  { id: "blk-080", name: "Makhana (Roasted Foxnuts) 100g", category: "Snacks", price: 160, stock: 26, rating: 4.5, keywords: ["foxnut"] },
  { id: "blk-081", name: "Oreo Original 120g", category: "Biscuits", price: 35, stock: 44, rating: 4.6 },
  { id: "blk-082", name: "Hide & Seek Chocolate 100g", category: "Biscuits", price: 40, stock: 40, rating: 4.5 },
  { id: "blk-083", name: "Good Day Butter Cookies 200g", category: "Biscuits", price: 55, stock: 38, rating: 4.4 },
  { id: "blk-084", name: "Bourbon Chocolate Cream Biscuits 150g", category: "Biscuits", price: 35, stock: 36, rating: 4.3 },
  { id: "blk-085", name: "Monaco Classic 200g", category: "Biscuits", price: 45, stock: 34, rating: 4.2 },
  { id: "blk-086", name: "50-50 Maska Chaska 200g", category: "Biscuits", price: 45, stock: 34, rating: 4.3 },
  { id: "blk-087", name: "Marie Gold 450g", category: "Biscuits", price: 65, stock: 30, rating: 4.2 },
  { id: "blk-088", name: "Nankhatai Cookies 250g", category: "Biscuits", price: 110, stock: 24, rating: 4.4 },
  { id: "blk-089", name: "Glucose Biscuits 800g", category: "Biscuits", price: 85, stock: 28, rating: 4.3 },
  { id: "blk-090", name: "Soan Papdi 500g", category: "Sweets", price: 220, stock: 18, rating: 4.1 },
  { id: "blk-091", name: "Hand Sanitizer 500ml", category: "Hygiene", price: 125, stock: 30, rating: 4.5 },
  { id: "blk-092", name: "Bath Soap (Pack of 4)", category: "Hygiene", price: 140, stock: 26, rating: 4.4 },
  { id: "blk-093", name: "Shampoo 340ml", category: "Hygiene", price: 199, stock: 22, rating: 4.3 },
  { id: "blk-094", name: "Toothbrush (Pack of 3)", category: "Hygiene", price: 90, stock: 28, rating: 4.4 },
  { id: "blk-095", name: "Toothpaste 200g", category: "Hygiene", price: 110, stock: 34, rating: 4.4 },
  { id: "blk-096", name: "Antiseptic Liquid 500ml", category: "Hygiene", price: 165, stock: 20, rating: 4.5 },
  { id: "blk-097", name: "Sanitary Pads (XL, 20 pads)", category: "Hygiene", price: 260, stock: 18, rating: 4.6 },
  { id: "blk-098", name: "Toilet Cleaner 1L", category: "Hygiene", price: 120, stock: 24, rating: 4.5 },
  { id: "blk-099", name: "Dishwash Liquid 750ml", category: "Hygiene", price: 140, stock: 26, rating: 4.4 },
  { id: "blk-100", name: "Tissues Box (2-ply, 100 pulls)", category: "Hygiene", price: 75, stock: 40, rating: 4.3 }
  ,
  // Added staples for popular Indian dishes (biryani, halwa, dosa, idli, vada pav, chole)
  { id: "blk-101", name: "Chicken Curry Cut 1kg", category: "Meat", price: 320, stock: 20, rating: 4.6, keywords: ["chicken", "curry cut", "chicken pieces"] },
  { id: "blk-102", name: "Eggs (Pack of 12)", category: "Dairy & Eggs", price: 78, stock: 30, rating: 4.5 },
  { id: "blk-103", name: "Idli Rice 1kg", category: "Staples", price: 65, stock: 40, rating: 4.6 },
  { id: "blk-104", name: "Idli Rice 5kg", category: "Staples", price: 295, stock: 16, rating: 4.7 },
  { id: "blk-105", name: "Urad Dal (Skinned) 1kg", category: "Pulses", price: 150, stock: 28, rating: 4.6 },
  { id: "blk-106", name: "Poha (Flattened Rice) 1kg", category: "Staples", price: 70, stock: 36, rating: 4.4 },
  { id: "blk-107", name: "Sooji / Rava 1kg", category: "Staples", price: 55, stock: 38, rating: 4.5 },
  { id: "blk-108", name: "Besan (Gram Flour) 1kg", category: "Staples", price: 90, stock: 34, rating: 4.6 },
  { id: "blk-109", name: "Idli / Dosa Batter 1kg", category: "Ready to Cook", price: 75, stock: 24, rating: 4.5, keywords: ["dosa batter", "idli batter"] },
  { id: "blk-110", name: "Pav Bread (6 pcs)", category: "Bakery", price: 35, stock: 30, rating: 4.3 },
  { id: "blk-111", name: "Kabuli Chana 1kg", category: "Pulses", price: 140, stock: 28, rating: 4.5 },
  { id: "blk-112", name: "Chole Masala 100g", category: "Spices", price: 85, stock: 30, rating: 4.6, keywords: ["chana masala"] },
  { id: "blk-113", name: "Tamarind 200g", category: "Staples", price: 45, stock: 26, rating: 4.4 },
  { id: "blk-114", name: "Jaggery (Gur) 500g", category: "Staples", price: 55, stock: 30, rating: 4.5 },
  { id: "blk-115", name: "Sugar 1kg", category: "Staples", price: 48, stock: 50, rating: 4.4 },
  { id: "blk-116", name: "Maida (Refined Flour) 1kg", category: "Staples", price: 55, stock: 36, rating: 4.3, keywords: ["refined flour"] },
  { id: "blk-117", name: "Rice Flour 500g", category: "Staples", price: 45, stock: 32, rating: 4.3 },
  { id: "blk-118", name: "Lemon (6 pcs)", category: "Fruits", price: 30, stock: 40, rating: 4.2, keywords: ["lime"] },
  { id: "blk-119", name: "Coconut (1 pc)", category: "Fruits", price: 45, stock: 22, rating: 4.1 }
  ,
  // More staples for dosa/idli/poha/pav bhaji/chole/halwa/snacks
  { id: "blk-120", name: "Moong Dal 1kg", category: "Pulses", price: 130, stock: 34, rating: 4.5 },
  { id: "blk-121", name: "Masoor Dal 1kg", category: "Pulses", price: 125, stock: 32, rating: 4.5, keywords: ["red lentils"] },
  { id: "blk-122", name: "Peanuts (Mungfali) 500g", category: "Snacks", price: 85, stock: 36, rating: 4.4 },
  { id: "blk-123", name: "Poha Thick 500g", category: "Staples", price: 40, stock: 34, rating: 4.4 },
  { id: "blk-124", name: "Idli Rava 1kg", category: "Staples", price: 65, stock: 28, rating: 4.4 },
  { id: "blk-125", name: "Pav Bhaji Masala 100g", category: "Spices", price: 85, stock: 30, rating: 4.6, keywords: ["pav bhaji"] },
  { id: "blk-126", name: "Black Tea Bags (25 pcs)", category: "Beverages", price: 60, stock: 30, rating: 4.3 },
  { id: "blk-127", name: "Baking Soda 100g", category: "Baking", price: 35, stock: 26, rating: 4.4 },
  { id: "blk-128", name: "Cauliflower 1 pc", category: "Vegetables", price: 45, stock: 30, rating: 4.2 },
  { id: "blk-129", name: "Capsicum (Green) 500g", category: "Vegetables", price: 55, stock: 32, rating: 4.3 },
  { id: "blk-130", name: "Frozen Green Peas 500g", category: "Frozen", price: 65, stock: 24, rating: 4.4, keywords: ["peas"] },
  { id: "blk-131", name: "Sev 200g", category: "Snacks", price: 55, stock: 28, rating: 4.3 },
  { id: "blk-132", name: "Murmura (Puffed Rice) 500g", category: "Staples", price: 45, stock: 30, rating: 4.4, keywords: ["puffed rice"] },
  { id: "blk-133", name: "Tamarind Chutney 200g", category: "Condiments", price: 65, stock: 22, rating: 4.3 },
  { id: "blk-134", name: "Coconut Milk 400ml", category: "Dairy Alternatives", price: 110, stock: 18, rating: 4.4, keywords: ["coconut milk"] },
  { id: "blk-135", name: "Almonds 500g", category: "Dry Fruits", price: 420, stock: 16, rating: 4.6, keywords: ["almond", "almonds", "badam", "sliced almond", "chopped almond", "whole almond"] },
  { id: "blk-136", name: "Cashews 500g", category: "Dry Fruits", price: 520, stock: 16, rating: 4.6 },
  { id: "blk-137", name: "Raisins 500g", category: "Dry Fruits", price: 220, stock: 18, rating: 4.5, keywords: ["kishmish"] },
  { id: "blk-138", name: "Semolina (Fine Rava) 500g", category: "Staples", price: 38, stock: 34, rating: 4.4 },
  { id: "blk-139", name: "Jaggery Powder 1kg", category: "Staples", price: 95, stock: 28, rating: 4.5 },
  { id: "blk-140", name: "Paneer 500g", category: "Dairy", price: 190, stock: 20, rating: 4.7 }
  ,
  // Tea / Coffee / Breakfast
  { id: "blk-141", name: "Assam Tea Loose 500g", category: "Beverages", price: 260, stock: 30, rating: 4.4, keywords: ["tea"] },
  { id: "blk-142", name: "Tea Masala 50g", category: "Spices", price: 70, stock: 24, rating: 4.5 },
  { id: "blk-143", name: "Instant Coffee 100g", category: "Beverages", price: 320, stock: 20, rating: 4.6 },
  { id: "blk-144", name: "Filter Coffee Powder 500g", category: "Beverages", price: 280, stock: 18, rating: 4.5 },
  { id: "blk-145", name: "Milk Powder 500g", category: "Dairy", price: 210, stock: 22, rating: 4.4 },
  { id: "blk-146", name: "Oats 1kg", category: "Breakfast", price: 180, stock: 30, rating: 4.5 },
  { id: "blk-147", name: "Muesli Fruit & Nut 750g", category: "Breakfast", price: 420, stock: 16, rating: 4.4 },
  { id: "blk-148", name: "Peanut Butter 1kg", category: "Breakfast", price: 320, stock: 20, rating: 4.5 },
  { id: "blk-149", name: "Mixed Fruit Jam 500g", category: "Breakfast", price: 135, stock: 26, rating: 4.4 },
  { id: "blk-150", name: "Whole Wheat Bread 400g", category: "Bakery", price: 45, stock: 34, rating: 4.2 },
  { id: "blk-151", name: "Multigrain Bread 400g", category: "Bakery", price: 55, stock: 28, rating: 4.3 },
  { id: "blk-152", name: "Veg Puff Pastry (Frozen) 6 pcs", category: "Frozen", price: 120, stock: 18, rating: 4.1 },
  { id: "blk-153", name: "Hash Browns (Frozen) 500g", category: "Frozen", price: 160, stock: 18, rating: 4.3 },
  { id: "blk-154", name: "Baked Beans 400g", category: "Breakfast", price: 95, stock: 22, rating: 4.2 },
  { id: "blk-155", name: "Porridge Mix (Sattu) 500g", category: "Breakfast", price: 85, stock: 24, rating: 4.4 },
  // Fixes for missed items / spelling variants
  { id: "blk-156", name: "Iodized Salt 1kg", category: "Staples", price: 28, stock: 60, rating: 4.4, keywords: ["salt"] },
  { id: "blk-157", name: "Ginger Garlic Paste 200g", category: "Spices", price: 85, stock: 30, rating: 4.5, keywords: ["ginger garlic paste", "ginger-garlic"] },
  { id: "blk-158", name: "Green Chilli 100g", category: "Vegetables", price: 18, stock: 45, rating: 4.2, keywords: ["green chili", "green chilli", "green chillies", "green chilies", "chili", "chilli"] },
  { id: "blk-159", name: "Fresh Coriander Leaves 100g", category: "Vegetables", price: 15, stock: 60, rating: 4.5, keywords: ["coriander", "coriander leaves", "dhania"] },
  { id: "blk-160", name: "Fresh Mint Leaves 100g", category: "Vegetables", price: 18, stock: 30, rating: 4.4, keywords: ["mint", "mint leaves", "pudina"] },
  { id: "blk-161", name: "Chicken Bone-in Curry Cut 1kg", category: "Meat", price: 325, stock: 20, rating: 4.6, keywords: ["chicken", "chicken curry cut", "chicken bone-in", "chicken pieces", "bone in pieces"] },
  { id: "blk-162", name: "Whole Spices Mix 100g (Bay Leaf, Cloves, Cinnamon, Cardamom)", category: "Spices", price: 95, stock: 28, rating: 4.6, keywords: ["whole spices", "bay leaf", "cloves", "cinnamon", "cardamom", "whole spices mix"] },
  // Items for Gajar Ka Halwa (Carrot Halwa)
  { id: "blk-163", name: "Carrot 500g", category: "Vegetables", price: 15, stock: 70, rating: 4.3, keywords: ["gajar", "carrots", "carrot"] },
  { id: "blk-164", name: "Sugar 500g", category: "Staples", price: 25, stock: 50, rating: 4.4, keywords: ["sugar", "chini"] },
  { id: "blk-165", name: "Desi Ghee 250ml", category: "Dairy", price: 220, stock: 20, rating: 4.8, keywords: ["ghee", "desi ghee", "clarified butter"] },
  { id: "blk-166", name: "Full Cream Milk 1L", category: "Dairy", price: 68, stock: 40, rating: 4.6, keywords: ["milk", "full cream milk", "doodh"] },
  { id: "blk-167", name: "Green Cardamom Pods 25g", category: "Spices", price: 95, stock: 20, rating: 4.7, keywords: ["cardamom", "elaichi", "green cardamom"] },
  { id: "blk-168", name: "Khoya / Mawa 500g", category: "Dairy", price: 280, stock: 18, rating: 4.6, keywords: ["khoya", "mawa", "khoya mawa"] },
  { id: "blk-169", name: "Mixed Dry Fruits 500g (Cashew, Almond, Raisin, Pistachio)", category: "Dry Fruits", price: 620, stock: 20, rating: 4.7, keywords: ["dry fruits", "nuts", "cashew", "almond", "raisin", "pistachio", "kaju", "badam", "kishmish"] },
  { id: "blk-170", name: "Condensed Milk 200g", category: "Dairy", price: 75, stock: 28, rating: 4.5, keywords: ["condensed milk", "milkmaid"] },
  // Items for Paneer Sabji (Paneer Curry)
  { id: "blk-171", name: "Paneer 250g", category: "Dairy", price: 105, stock: 24, rating: 4.7, keywords: ["paneer", "cottage cheese"] },
  { id: "blk-172", name: "Paneer Masala 100g", category: "Spices", price: 90, stock: 32, rating: 4.6, keywords: ["paneer masala", "paneer sabji masala", "paneer curry masala"] },
  { id: "blk-173", name: "Kasuri Methi 50g", category: "Spices", price: 75, stock: 30, rating: 4.5, keywords: ["kasuri methi", "dried fenugreek leaves", "methi"] },
  { id: "blk-174", name: "Fresh Cream 100ml", category: "Dairy", price: 40, stock: 32, rating: 4.6, keywords: ["cream", "fresh cream", "malai"] },
  { id: "blk-175", name: "Tomato 500g", category: "Vegetables", price: 18, stock: 70, rating: 4.2, keywords: ["tomato", "tomatoes"] },
  { id: "blk-176", name: "Onion 500g", category: "Vegetables", price: 22, stock: 80, rating: 4.1, keywords: ["onion", "onions", "pyaz"] },
  { id: "blk-177", name: "Ginger 100g", category: "Vegetables", price: 15, stock: 40, rating: 4.3, keywords: ["ginger", "adrak"] },
  { id: "blk-178", name: "Garlic 100g", category: "Vegetables", price: 12, stock: 50, rating: 4.4, keywords: ["garlic", "lehsun"] },
  { id: "blk-179", name: "Paneer Tikka Masala Paste 100g", category: "Ready to Cook", price: 65, stock: 20, rating: 4.4, keywords: ["paneer tikka masala", "paneer curry paste"] },
  { id: "blk-180", name: "Butter 200g", category: "Dairy", price: 115, stock: 22, rating: 4.6, keywords: ["butter", "makhan"] }
];

const tools = [
  {
    name: "blinkit.search",
    description: "Search the dummy Blinkit catalog by name or category",
    input_schema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Text to match against name or category" },
        limit: { type: "number", description: "Maximum items to return (default 5)" }
      },
      required: ["query"]
    }
  },
  {
    name: "blinkit.item",
    description: "Get a single catalog item by id",
    input_schema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Catalog id such as blk-001" }
      },
      required: ["id"]
    }
  },
  {
    name: "blinkit.add_to_cart",
    description: "Add an item to the in-memory demo cart",
    input_schema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Catalog id" },
        quantity: { type: "number", description: "Units to add", minimum: 1, default: 1 }
      },
      required: ["id", "quantity"]
    }
  },
  {
    name: "blinkit.cart",
    description: "View the in-memory demo cart summary",
    input_schema: {
      type: "object",
      properties: {},
      additionalProperties: false
    }
  },
  {
    name: "blinkit.clear_cart",
    description: "Clear all items from the cart (typically called after successful payment)",
    input_schema: {
      type: "object",
      properties: {},
      additionalProperties: false
    }
  },
  {
    name: "blinkit.list_discounts",
    description: "List Blinkit promo codes eligible for the given cart/order amount (use at checkout)",
    input_schema: {
      type: "object",
      properties: {
        amount: { type: "number", description: "Order/cart total in INR" },
        orderId: { type: "string", description: "Optional order id" }
      },
      required: ["amount"]
    }
  },
  {
    name: "blinkit.apply_discount",
    description: "Apply a Blinkit discount code and get the final amount to pay",
    input_schema: {
      type: "object",
      properties: {
        code: { type: "string", description: "Discount code (e.g. FIRST50, BLINK10)" },
        amount: { type: "number", description: "Order total in INR before discount" },
        orderId: { type: "string", description: "Optional order id" }
      },
      required: ["code", "amount"]
    }
  }
];

const cart = new Map();

function searchCatalog(query, limit = 5) {
  const q = (query || "").trim();
  if (!q) return [];
  const normalized = q.toLowerCase();
  // Escape regex specials, then allow whitespace to fuzzily match
  const escaped = normalized.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const fuzzy = new RegExp(escaped.replace(/\s+/g, ".*"), "i");

  // Extract significant words (filter out common descriptive words like "sliced", "chopped", "diced", etc.)
  const descriptiveWords = new Set(["sliced", "chopped", "diced", "whole", "raw", "fresh", "dried", "roasted", "salted", "unsalted", "organic", "pack", "packet", "box", "bottle", "jar", "can", "tin"]);
  const queryWords = normalized.split(/\s+/).filter(word => word.length > 2 && !descriptiveWords.has(word));
  // If all words were filtered out, use the original normalized query
  const significantQuery = queryWords.length > 0 ? queryWords.join(" ") : normalized;

  return catalog
    .filter((item) => {
      const itemNameLower = item.name.toLowerCase();
      const itemCategoryLower = item.category.toLowerCase();
      
      // Full query match (original behavior)
      const nameMatch = itemNameLower.includes(normalized) || fuzzy.test(item.name);
      const catMatch = itemCategoryLower.includes(normalized) || fuzzy.test(item.category);
      
      // Significant word match (handles "sliced almond" -> matches "almond")
      const significantNameMatch = queryWords.length > 0 && 
        queryWords.some(word => itemNameLower.includes(word) || new RegExp(word, "i").test(item.name));
      const significantCatMatch = queryWords.length > 0 && 
        queryWords.some(word => itemCategoryLower.includes(word));
      
      // Improved keyword matching: check both directions (keyword contains query OR query contains keyword)
      // This handles singular/plural variations (e.g., "carrot" matches "carrots" and vice versa)
      const keywordMatch = Array.isArray(item.keywords)
        ? item.keywords.some((k) => {
            const kLower = k.toLowerCase();
            // Check full query match
            if (fuzzy.test(k) || kLower.includes(normalized) || normalized.includes(kLower)) {
              return true;
            }
            // Check significant word match (handles "sliced almond" matching "almond" keyword)
            if (queryWords.length > 0) {
              return queryWords.some(word => kLower.includes(word) || word.includes(kLower));
            }
            return false;
          })
        : false;
      
      return nameMatch || catMatch || keywordMatch || significantNameMatch || significantCatMatch;
    })
    .slice(0, limit);
}

function getItem(id) {
  return catalog.find((item) => item.id === id);
}

function addToCart(id, quantity) {
  const item = getItem(id);
  if (!item) throw new Error("Item not found");
  if (quantity < 1) throw new Error("Quantity must be >= 1");
  if (quantity > item.stock) throw new Error("Not enough stock");
  const current = cart.get(id) ?? { item, quantity: 0 };
  const nextQty = current.quantity + quantity;
  if (nextQty > item.stock) throw new Error("Not enough stock");
  cart.set(id, { item, quantity: nextQty });
  return cart.get(id);
}

function cartSummary() {
  const lines = [];
  let total = 0;
  for (const { item, quantity } of cart.values()) {
    const lineTotal = item.price * quantity;
    total += lineTotal;
    lines.push({ id: item.id, name: item.name, quantity, unitPrice: item.price, lineTotal });
  }
  return { items: lines, total };
}

function clearCart() {
  const itemCount = cart.size;
  cart.clear();
  return { cleared: true, itemsRemoved: itemCount };
}

// --- Blinkit discounts (domain-specific, applied at checkout) -----------------
const BLINKIT_DISCOUNTS = [
  { code: "FIRST50", description: "₹50 off on orders above ₹300", minAmount: 300, type: "flat", value: 50 },
  { code: "BLINK10", description: "10% off on orders above ₹500", minAmount: 500, type: "percent", value: 10 },
  { code: "SAVE100", description: "₹100 off on orders above ₹1000", minAmount: 1000, type: "flat", value: 100 },
];

function listBlinkitDiscounts(amount, orderId) {
  const amt = Number(amount) || 0;
  const eligible = BLINKIT_DISCOUNTS.filter((d) => amt >= d.minAmount).map((d) => {
    let discountAmount = 0;
    if (d.type === "flat") discountAmount = Math.min(d.value, amt);
    else if (d.type === "percent") discountAmount = Math.round((amt * d.value) / 100);
    const finalAmount = Math.max(0, amt - discountAmount);
    return { code: d.code, description: d.description, discountAmount, finalAmount, originalAmount: amt };
  });
  return { discounts: eligible };
}

function applyBlinkitDiscount(code, amount, orderId) {
  const amt = Number(amount) || 0;
  const discount = BLINKIT_DISCOUNTS.find((d) => d.code === (code || "").trim().toUpperCase());
  if (!discount || amt < discount.minAmount) {
    return { valid: false, finalAmount: amt, message: discount ? `Minimum order ₹${discount.minAmount} for ${discount.code}` : "Invalid or expired code" };
  }
  let discountAmount = 0;
  if (discount.type === "flat") discountAmount = Math.min(discount.value, amt);
  else if (discount.type === "percent") discountAmount = Math.round((amt * discount.value) / 100);
  const finalAmount = Math.max(0, amt - discountAmount);
  return { valid: true, finalAmount, discountAmount, message: `${discount.code} applied. You pay ₹${finalAmount}` };
}

function respond(id, result) {
  process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, result }) + "\n");
}

function respondError(id, code, message) {
  process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, error: { code, message } }) + "\n");
}

const rl = readline.createInterface({ input: process.stdin });

rl.on("line", (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;
  let msg;
  try {
    msg = JSON.parse(trimmed);
  } catch (err) {
    respondError(null, -32700, `Invalid JSON: ${err.message}`);
    return;
  }

  const { id = null, method, params = {} } = msg;
  try {
    switch (method) {
      case "initialize": {
        respond(id, {
          serverInfo: { name: "blinkit-mcp", version: "0.1.0" },
          capabilities: { tools: { list: true, call: true } }
        });
        break;
      }
      case "tools/list": {
        respond(id, { tools });
        break;
      }
      case "tools/call": {
        const { name, arguments: args = {} } = params;
        if (!name) throw new Error("Missing tool name");
        let content;
        switch (name) {
          case "blinkit.search": {
            const results = searchCatalog(args.query ?? "", args.limit ?? 5);
            content = [{ type: "text", text: JSON.stringify(results, null, 2) }];
            break;
          }
          case "blinkit.item": {
            const item = getItem(args.id);
            if (!item) throw new Error("Item not found");
            content = [{ type: "text", text: JSON.stringify(item, null, 2) }];
            break;
          }
          case "blinkit.add_to_cart": {
            const entry = addToCart(args.id, Number(args.quantity ?? 1));
            content = [{ type: "text", text: JSON.stringify(entry, null, 2) }];
            break;
          }
          case "blinkit.cart": {
            content = [{ type: "text", text: JSON.stringify(cartSummary(), null, 2) }];
            break;
          }
          case "blinkit.clear_cart": {
            const result = clearCart();
            content = [{ type: "text", text: JSON.stringify(result, null, 2) }];
            break;
          }
          case "blinkit.list_discounts": {
            const result = listBlinkitDiscounts(args.amount, args.orderId);
            content = [{ type: "text", text: JSON.stringify(result, null, 2) }];
            break;
          }
          case "blinkit.apply_discount": {
            const result = applyBlinkitDiscount(args.code, args.amount, args.orderId);
            content = [{ type: "text", text: JSON.stringify(result, null, 2) }];
            break;
          }
          default:
            throw new Error(`Unknown tool: ${name}`);
        }
        respond(id, { content });
        break;
      }
      default:
        respondError(id, -32601, `Unknown method: ${method}`);
    }
  } catch (err) {
    respondError(id, -32000, err?.message ?? "Unexpected error");
  }
});

rl.on("close", () => process.exit(0));

